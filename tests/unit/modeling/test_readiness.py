from dataclasses import replace
from datetime import UTC, datetime

import pytest

from domain_kernel import (
    Approval,
    ApprovalId,
    BundleId,
    BusinessCode,
    CandidateId,
    CandidatePin,
    DecisionId,
    DefinitionStatus,
    DomainModelBuilder,
    DomainModelBundle,
    EvidenceBasis,
    Issue,
    LabelText,
    MeaningText,
    ModelId,
    ModelInfo,
    ModelKind,
    ModelScope,
    ProjectId,
    Publication,
    PublicationId,
    QuestionId,
    StaleStateError,
    ValidationReportId,
    ValueSetMember,
    ValueSetMembership,
)
from domain_kernel.modeling.application.validation import validate_candidate
from domain_kernel.modeling.domain.comparison import compare_candidates
from domain_kernel.modeling.domain.publications import require_current_publication
from domain_kernel.modeling.domain.snapshots import (
    Candidate,
    ModelContent,
    PublicationRules,
    ReviewSnapshot,
    ValidationReport,
    VisibleQuestion,
)
from domain_kernel.modeling.domain.validation import (
    ModelAcceptanceEvaluator,
    ModelInvariantValidator,
    ModelReadinessEvaluator,
)
from domain_kernel.shared.domain.enums.check_outcome import CheckOutcome
from domain_kernel.shared.domain.enums.check_requirement import CheckRequirement
from domain_kernel.shared.domain.value_objects.acceptance_check_definition import (
    AcceptanceCheckDefinition,
)
from domain_kernel.shared.domain.value_objects.manual_criterion import ManualCriterion
from domain_kernel.shared.domain.value_objects.plans.create_definition import CreateDefinition
from domain_kernel.shared.domain.value_objects.quantity_required_check import QuantityRequiredCheck
from domain_kernel.shared.hashing import Hashing


@pytest.fixture
def candidate() -> Candidate:
    scope = ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="model"))
    info = ModelInfo(
        scope=scope,
        name="observed",
        display_name="Observed",
        kind=ModelKind.OBSERVED,
        description="Reviewed durations.",
        created_at=datetime.now(tz=UTC),
        revision=3,
    )
    builder = DomainModelBuilder(model_info=info)
    hour = builder.add_unit(name="hour", meaning="Elapsed hour.", symbol="h")
    units = builder.add_value_set(
        name="units",
        meaning="Local duration unit codes.",
        membership=ValueSetMembership.CLOSED,
        members=[
            ValueSetMember(
                code=BusinessCode(value="h"),
                label=LabelText(value="Hour"),
                meaning=MeaningText(value="Elapsed hour."),
                unit=hour,
            )
        ],
    )
    quantity = builder.add_quantity(name="duration", units=units, meaning="Processing duration.")
    _ = builder.add_definition(
        name="required-quantity",
        meaning="Verify the exact quantity.",
        body=AcceptanceCheckDefinition(
            statement=MeaningText(value="A measured duration requires a closed unit choice."),
            requirement=CheckRequirement.REQUIRED,
            predicate=QuantityRequiredCheck(structure=quantity),
        ),
    )
    _ = builder.add_definition(
        name="human-scope",
        meaning="Review interpretation locally.",
        body=AcceptanceCheckDefinition(
            statement=MeaningText(value="A reviewer checks the allocation against the policy."),
            requirement=CheckRequirement.ADVISORY,
            predicate=ManualCriterion(),
        ),
    )
    definitions = [
        replace(item.draft(scope=scope), status=DefinitionStatus.APPROVED)
        for item in builder.build_change_plan(reason="Inspect the quantity graph.").operations
        if isinstance(item, CreateDefinition)
    ]
    return Candidate(
        id=CandidateId(value="candidate"),
        scope=scope,
        kind=info.kind,
        description=info.description,
        workspace_revision=info.revision,
        review_snapshot_version=1,
        review_snapshot_hash=Hashing.hash_bytes(content=b"review"),
        content_hash=Hashing.hash_bytes(content=b"candidate"),
        content=ModelContent(definitions=definitions),
    )


def test_local_quantity_passes_and_human_judgement_remains_unknown(candidate: Candidate) -> None:
    results = ModelAcceptanceEvaluator().evaluate(candidate=candidate)
    assert tuple(result.outcome for result in results) == (CheckOutcome.PASS, CheckOutcome.UNKNOWN)
    assert all(result.candidate_hash == candidate.content_hash for result in results)


@pytest.mark.parametrize(
    "outcome",
    [
        CheckOutcome.FAIL,
        CheckOutcome.UNKNOWN,
        CheckOutcome.UNSUPPORTED,
        CheckOutcome.ERROR,
    ],
)
def test_readiness_blocks_each_unverified_required_outcome(
    candidate: Candidate,
    outcome: CheckOutcome,
) -> None:
    quantity, manual = ModelAcceptanceEvaluator().evaluate(candidate=candidate)
    validation = ValidationReport(
        id=ValidationReportId(value="report"),
        scope=candidate.scope,
        candidate_id=candidate.id,
        candidate_hash=candidate.content_hash,
        validator_fingerprint="core-1",
        reference_pack=None,
        issues=(),
        acceptance=(replace(quantity, outcome=outcome), manual),
    )
    review = ReviewSnapshot(
        scope=candidate.scope,
        version=candidate.review_snapshot_version,
        content_hash=candidate.review_snapshot_hash,
        decisions=(),
        pending_required=0,
    )
    readiness = ModelReadinessEvaluator().evaluate(
        candidate=candidate,
        validation=validation,
        reference_pack=None,
        review=review,
        rules=PublicationRules(),
    )
    assert not readiness.ready
    assert len(readiness.blockers) == 1
    assert readiness.blockers[0].path == ("definitions", quantity.definition_id.value)


def test_malformed_graph_evidence_and_confirmation_are_separate_findings(
    candidate: Candidate,
) -> None:
    definitions = tuple(item for item in candidate.content.definitions if item.name != "hour")
    definitions = tuple(
        replace(item, basis=EvidenceBasis.DOCUMENTED)
        if item.name == "duration"
        else replace(item, basis=EvidenceBasis.STATEMENT)
        if item.name == "units"
        else item
        for item in definitions
    )
    stale = replace(candidate, content=ModelContent(definitions=definitions))
    issues = ModelInvariantValidator().validate(candidate=stale, reference_pack=None)

    assert {"evidence_unavailable", "confirmation_unavailable"} <= {issue.code for issue in issues}
    assert any(issue.path[-1] == "unit" for issue in issues)
    result, _ = ModelAcceptanceEvaluator().evaluate(candidate=stale)
    assert result.outcome is CheckOutcome.FAIL


def test_reviewed_optional_questions_cannot_waive_required_gaps(candidate: Candidate) -> None:
    question = VisibleQuestion(
        id=QuestionId(value="question"),
        text="Which audit team uses the report?",
        scope_text="Reports",
        rationale="The team label is outside this contract.",
        reviewer="reviewer",
        decision_id=DecisionId(value="decision"),
    )
    selected = replace(candidate, nonblocking_questions=(question,))
    review = ReviewSnapshot(
        scope=selected.scope,
        version=selected.review_snapshot_version,
        content_hash=selected.review_snapshot_hash,
        decisions=(),
        pending_required=1,
        questions=(question,),
    )
    validation = ValidationReport(
        id=ValidationReportId(value="report"),
        scope=selected.scope,
        candidate_id=selected.id,
        candidate_hash=selected.content_hash,
        validator_fingerprint="core-1",
        reference_pack=None,
        issues=(),
        acceptance=ModelAcceptanceEvaluator().evaluate(candidate=selected),
    )
    policy = ModelReadinessEvaluator()
    blocked = policy.evaluate(
        candidate=selected,
        validation=validation,
        reference_pack=None,
        review=review,
        rules=PublicationRules(allow_reviewed_nonblocking_questions=True),
    )
    assert blocked.nonblocking_questions == (question,)
    assert {issue.code for issue in blocked.blockers} == {"required_review_pending"}
    mismatched = policy.evaluate(
        candidate=selected,
        validation=replace(validation, candidate_id=CandidateId(value="different")),
        reference_pack=None,
        review=replace(review, pending_required=0),
        rules=PublicationRules(allow_reviewed_nonblocking_questions=True),
    )
    assert {issue.code for issue in mismatched.blockers} == {"snapshot_mismatch"}


def test_release_binds_only_the_ready_candidate_and_verified_approval(candidate: Candidate) -> None:
    validation = validate_candidate(candidate=candidate)
    review = ReviewSnapshot(
        scope=candidate.scope,
        version=candidate.review_snapshot_version,
        content_hash=candidate.review_snapshot_hash,
        decisions=(),
        pending_required=0,
        questions=(),
    )
    readiness = ModelReadinessEvaluator().evaluate(
        candidate=candidate,
        validation=validation,
        reference_pack=None,
        review=review,
        rules=PublicationRules(allow_reviewed_nonblocking_questions=True),
    )
    assert readiness.ready
    now = datetime.now(tz=UTC)
    changes = compare_candidates(
        before=None,
        after=candidate,
        before_pin=None,
        after_pin=CandidatePin(
            scope=candidate.scope,
            candidate_id=candidate.id,
            content_hash=candidate.content_hash,
        ),
    )
    preparation = Publication(
        id=PublicationId(value="preparation"),
        scope=candidate.scope,
        candidate=candidate,
        reference_pack=None,
        validation=validation,
        readiness=readiness,
        changes=changes,
        policy_fingerprint="policy",
        prepared_at=now,
    )
    approval = Approval(
        id=ApprovalId(value="approved"),
        scope=candidate.scope,
        publication_id=preparation.id,
        candidate_id=candidate.id,
        candidate_hash=candidate.content_hash,
        validation_id=validation.id,
        workspace_revision=candidate.workspace_revision,
        review_snapshot_version=candidate.review_snapshot_version,
        policy_fingerprint=preparation.policy_fingerprint,
        actor="publisher",
        reason="Release reviewed definitions.",
        approved_at=now,
    )
    bundle = DomainModelBundle(
        id=BundleId(value="bundle"),
        scope=candidate.scope,
        version="1.0",
        publication=preparation,
        approval=approval,
        content_hash=Hashing.hash_bytes(content=b"bundle"),
        published_at=now,
    )
    assert bundle.approval is approval
    assert bundle.publication is preparation
    assert bundle.content is candidate.content
    other_scope = replace(candidate.scope, model_id=ModelId(value="foreign"))
    for invalid_approval in (
        replace(approval, scope=other_scope),
        replace(approval, candidate_id=CandidateId(value="different")),
        replace(approval, candidate_hash=Hashing.hash_bytes(content=b"changed")),
        replace(approval, validation_id=ValidationReportId(value="different")),
        replace(approval, review_snapshot_version=approval.review_snapshot_version + 1),
        replace(approval, policy_fingerprint="changed"),
    ):
        with pytest.raises(ValueError, match="exact ready preparation"):
            _ = replace(bundle, approval=invalid_approval)
    blocked = replace(
        preparation,
        readiness=replace(
            readiness,
            ready=False,
            blockers=[Issue(code="blocked", path=("review",), message="Required review.")],
        ),
    )
    with pytest.raises(ValueError, match="exact ready preparation"):
        _ = replace(bundle, publication=blocked)
    with pytest.raises(StaleStateError):
        require_current_publication(
            publication=preparation,
            current=replace(candidate, workspace_revision=candidate.workspace_revision + 1),
            policy_fingerprint=preparation.policy_fingerprint,
        )
