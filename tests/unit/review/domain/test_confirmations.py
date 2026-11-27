"""Exercise confirmation and mandatory question policy on detached records."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from domain_kernel import (
    CaseKind,
    CaseStatus,
    ConceptDefinition,
    ConfirmationMethod,
    DecisionId,
    Definition,
    DefinitionId,
    DefinitionStatus,
    Evidence,
    EvidenceId,
    Exclude,
    InvalidDecisionError,
    KeepNonblockingQuestion,
    ModelId,
    ModelScope,
    ObligationId,
    Person,
    PersonId,
    ProcessingRecord,
    ProjectId,
    ProposalId,
    Question,
    QuestionId,
    ReferencePackPin,
    Reject,
    RequirementKind,
    ReviewCase,
    ReviewCaseId,
    ReviewRequirement,
    SourceId,
    SourceRevision,
    SourceRevisionId,
    StatementForm,
    StatementIntent,
    StatementOrigin,
    StatementSpan,
)
from domain_kernel.review.domain.decisions import ConfirmStatement
from domain_kernel.review.domain.models import preview_case
from domain_kernel.review.domain.occurrences import source_effects
from domain_kernel.shared.domain.enums.source_disposition import SourceDisposition
from domain_kernel.shared.domain.value_objects.source_alignment import SourceAlignment
from domain_kernel.shared.hashing import Hashing
from domain_kernel.sources.domain.models import FileOrigin

_AT = datetime(year=2024, month=1, day=1, hour=14, tzinfo=UTC)
_RECORDED = datetime(year=2024, month=1, day=2, hour=14, tzinfo=UTC)
_SCOPE = ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="model"))
_ORIGIN = StatementOrigin(
    speaker=Person(id=PersonId(value="model-owner"), name="Aria", role="Application owner"),
    recorded_by="recorder",
    stated_at=_AT,
    recorded_at=_RECORDED,
    context="Inventory meaning.",
    form=StatementForm.QUOTATION,
    intent=StatementIntent.ASSERTION,
)


def _revision(*, origin: StatementOrigin | FileOrigin = _ORIGIN) -> SourceRevision:
    return SourceRevision(
        project_id=_SCOPE.project_id,
        source_id=SourceId(value="statement"),
        revision_id=SourceRevisionId(value=Hashing.hash_bytes(content=b"statement").value),
        byte_length=9,
        origin=origin,
    )


def _evidence(*, revision: SourceRevision) -> Evidence:
    return Evidence(
        id=EvidenceId(value="cite"),
        source=revision,
        locator=StatementSpan(start=0, end=9),
        processing=ProcessingRecord(
            source=revision,
            fingerprint="statement-parser",
            parser_id="statement",
            parser_version="1",
        ),
    )


def _confirm(*, revision: SourceRevision, evidence: list[Evidence]) -> ConfirmStatement:
    # The pure domain factory is exercised independently of the public source adapter.
    return ConfirmStatement._from_statement(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        revision=revision,
        evidence=evidence,
        authority="Model owner",
        reason="Review the meaning.",
    )


def test_confirmation_detaches_the_exact_attributed_capture() -> None:
    revision = _revision()
    citation = _evidence(revision=revision)
    evidence = [citation]
    confirmation = _confirm(revision=revision, evidence=evidence).confirmation
    evidence.clear()
    assert confirmation.evidence == (citation,)
    assert confirmation.confirmed_at == _AT
    assert confirmation.recorded_at == _RECORDED
    assert confirmation.confirmed_by == _ORIGIN.speaker
    assert confirmation.recorded_by == _ORIGIN.recorded_by
    assert confirmation.method is ConfirmationMethod.RECORDED
    assert confirmation.authenticated_actor is None


def test_confirmation_rejects_absent_or_incompatible_captures() -> None:
    exact = _revision()
    unknown = _revision(origin=replace(_ORIGIN, stated_at=None))
    file = _revision(
        origin=FileOrigin(
            reader="reader",
            provider_scope="provider",
            location="source.pdf",
            provider_version=None,
            acquired_at=_RECORDED,
        )
    )
    later = replace(
        exact, revision_id=SourceRevisionId(value=Hashing.hash_bytes(content=b"other").value)
    )
    for revision, evidence in (
        (exact, []),
        (exact, [_evidence(revision=later)]),
        (unknown, [_evidence(revision=unknown)]),
        (file, [_evidence(revision=file)]),
    ):
        with pytest.raises(InvalidDecisionError):
            _ = _confirm(revision=revision, evidence=evidence)


def test_required_pack_gap_cannot_become_nonblocking() -> None:
    obligation = ObligationId(value="coverage")
    pin = ReferencePackPin(
        key="pack", version="1", content_hash=Hashing.hash_bytes(content=b"pack")
    )
    case = ReviewCase(
        id=ReviewCaseId(value="case"),
        scope=_SCOPE,
        kind=CaseKind.QUESTION,
        status=CaseStatus.DEFERRED,
        version=2,
        reason="Review a required pack obligation.",
        definitions=(),
        question=Question(
            id=QuestionId(value="q"),
            text="Which definition satisfies coverage?",
            required=False,
            scope_text="Inventory",
            obligation_id=obligation,
            evidence=(),
        ),
        requirements=[
            ReviewRequirement(
                kind=RequirementKind.REFERENCE_PACK,
                code="coverage",
                required=True,
                reference_pack=pin,
                obligation_id=obligation,
            ),
        ],
    )
    with pytest.raises(InvalidDecisionError, match="Resolve required"):
        _ = preview_case(
            case=case,
            decision=KeepNonblockingQuestion(scope_text="Inventory", reason="Defer."),
        )


def test_correction_retains_the_other_effect_of_a_grouped_decision() -> None:
    citation = _evidence(revision=_revision())
    target = Definition(
        id=DefinitionId(value="material"),
        scope=_SCOPE,
        revision=2,
        name="material",
        display_name="Material",
        meaning="Material as recorded by the application.",
        body=ConceptDefinition(),
        status=DefinitionStatus.APPROVED,
    )
    original = ReviewCase(
        id=ReviewCaseId(value="original"),
        scope=_SCOPE,
        kind=CaseKind.SOURCE_ALIGNMENT,
        status=CaseStatus.RESOLVED,
        version=2,
        reason="Inspect two compatible source descriptions.",
        definitions=(target,),
        proposal_ids=(ProposalId(value="first"), ProposalId(value="second")),
        context_fingerprint="source-context",
        evidence=(citation,),
    )
    predecessor = DecisionId(value="earlier")
    before = {
        identity: SourceAlignment(
            proposal_id=identity,
            definition_id=target.id,
            definition_revision=target.revision,
            disposition=SourceDisposition.MAPPED,
            decision_id=predecessor,
            rationale="Earlier reasoning.",
            context_fingerprint="source-context",
            evidence=(citation,),
        )
        for identity in original.proposal_ids
    }
    chosen = original.proposal_ids[1]
    selected = replace(
        original,
        version=1,
        status=CaseStatus.PENDING,
        id=ReviewCaseId(value="correction"),
        proposal_ids=(chosen,),
        correction_of_case_id=original.id,
        correction_of_decision_id=predecessor,
    )
    (change,) = source_effects(
        case=selected,
        decision=Exclude(scope_text="Historical stock", reason="Outside the current study."),
        effective=before,
    )
    assert change.before == before[chosen]
    assert change.after is not None
    assert change.after.proposal_id == chosen
    assert change.after.evidence == (citation,)
    assert (
        source_effects(case=selected, decision=Reject(reason="Keep prior."), effective=before) == ()
    )
