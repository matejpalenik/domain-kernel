from dataclasses import replace
from datetime import UTC, datetime

import pytest

from domain_kernel import (
    BusinessCode,
    CandidateId,
    DecisionId,
    DefinitionStatus,
    DomainModelBuilder,
    EvidenceBasis,
    LabelText,
    MeaningText,
    ModelId,
    ModelInfo,
    ModelKind,
    ModelScope,
    ProjectId,
    QuestionId,
    ValidationReportId,
    ValueSetMember,
    ValueSetMembership,
)
from domain_kernel._shared.domain.acceptance import (
    AcceptanceCheckDefinition,
    CheckOutcome,
    CheckRequirement,
    ManualCriterion,
    QuantityRequiredCheck,
)
from domain_kernel._shared.domain.authoring import CreateDefinition
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
from domain_kernel.shared.hashing import hash_bytes


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
        review_snapshot_hash=hash_bytes(content=b"review"),
        content_hash=hash_bytes(content=b"candidate"),
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
