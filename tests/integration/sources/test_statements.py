"""Exercise immutable attributed statements at the source API boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    CaseStatus,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DomainModelBundle,
    EvidenceBasis,
    EvidenceUnavailableError,
    IdempotencyConflictError,
    ModelKind,
    Person,
    PersonId,
    ScopeMismatchError,
    SourceInput,
    Statement,
    StatementForm,
    StatementIntent,
    StatementOrigin,
    StatementSpan,
)

if TYPE_CHECKING:
    from pathlib import Path


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
_TEXT = "Provision codes locate application records."
_SPEAKER = Person(id=PersonId(value="developer"), name="Ari Novak", role="Application owner")


def _statement(
    *,
    context: str = "Recruitment citations",
    recorded_by: str | None = None,
    stated_at: datetime | None = None,
) -> Statement:
    return Statement(
        text=_TEXT,
        speaker=_SPEAKER,
        recorded_by=recorded_by,
        stated_at=stated_at,
        context=context,
        form=StatementForm.QUOTATION,
        intent=StatementIntent.ASSERTION,
    )


async def test_attribution_is_captured_once_and_exact_evidence_reopens(tmp_path: Path) -> None:
    config = ClientConfiguration(base_dir=tmp_path)
    project = await Client(config=config).create_project(actor="owner", name="recruitment")
    captured = await project.ingest_source(
        actor="scribe",
        name="locator",
        source=_statement(),
        idempotency_key="locator-first",
    )
    origin = captured.revision.origin
    assert isinstance(origin, StatementOrigin)
    assert origin.speaker == _SPEAKER
    assert origin.recorded_by == "scribe"
    assert origin.stated_at is None
    assert origin.recorded_at.utcoffset() is not None
    (citation,) = captured.evidence
    assert citation.locator == StatementSpan(start=0, end=len(_TEXT))

    reopened = await Client(config=config).get_project(name=project.name)
    retry = await reopened.ingest_source(
        actor="scribe",
        name="locator",
        source=_statement(),
        idempotency_key="locator-first",
    )
    assert retry == captured
    assert retry.revision.origin == origin
    exact = await reopened.get_evidence(evidence=citation)
    assert exact.excerpt == _TEXT
    assert exact.origin == origin
    assert _TEXT not in repr(exact)
    assert _TEXT not in repr(_statement())

    model = await reopened.create_model(
        actor="designer",
        name="locators",
        kind=ModelKind.PROPOSED,
        description="Application-defined locators used in correspondence.",
    )
    proposal = await model.propose_definition(
        actor="designer",
        name="provision-code",
        meaning="An application-local citation locator.",
        body=ConceptDefinition(),
        evidence=[citation],
        reason="Inspect the attributed clarification.",
    )
    assert proposal.status is CaseStatus.PENDING
    assert proposal.definitions[0].basis is EvidenceBasis.HYPOTHESIS
    assert (await model.get_review_case(case_id=proposal.id)).definitions[0].evidence == (citation,)

    _ = await model.decide_review(
        actor="reviewer",
        case=proposal,
        decision=Accept(reason="Use the local definition."),
    )
    prepared = await model.prepare_publication(actor="publisher")
    published = await model.publish(
        actor="publisher",
        publication=prepared,
        version="1.0.0",
        reason="Publish local locators.",
    )
    portable = published.serialize()
    assert _TEXT.encode() not in portable
    detached = DomainModelBundle.deserialize(payload=portable.decode())
    restored = detached.get_concept(name="provision-code")
    assert restored.evidence == (citation,)
    assert restored.basis is EvidenceBasis.HYPOTHESIS

    revised = await reopened.ingest_source_revision(
        actor="editor",
        source_id=captured.source_id,
        source=_statement(
            context="Applicant correspondence", stated_at=datetime(2026, 11, 17, tzinfo=UTC)
        ),
    )
    assert revised.source_id == captured.source_id
    assert revised.revision_id != captured.revision_id
    assert isinstance(revised.revision.origin, StatementOrigin)
    assert revised.revision.origin.recorded_by == "editor"
    assert await reopened.get_evidence(evidence=citation) == exact

    with pytest.raises(IdempotencyConflictError):
        _ = await reopened.ingest_source(
            actor="scribe",
            name="locator",
            source=_statement(context="Different context"),
            idempotency_key="locator-first",
        )
    with pytest.raises(EvidenceUnavailableError):
        _ = await reopened.get_evidence(
            evidence=replace(citation, locator=StatementSpan(start=1, end=len(_TEXT))),
        )
    foreign = await Client(config=config).create_project(actor="owner", name="other")
    with pytest.raises(ScopeMismatchError):
        _ = await foreign.get_evidence(evidence=citation)


async def test_statement_batch_preserves_explicit_and_default_recorders(tmp_path: Path) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="owner",
        name="recruitment",
    )
    results = await project.ingest_sources(
        actor="batch-recorder",
        sources=[
            SourceInput(name="default", source=_statement()),
            SourceInput(name="explicit", source=_statement(recorded_by="named-scribe")),
        ],
    )
    first, named = (item.ingested_source.revision for item in results.successes)
    assert isinstance(first.origin, StatementOrigin)
    assert isinstance(named.origin, StatementOrigin)
    assert first.origin.recorded_by == "batch-recorder"
    assert named.origin.recorded_by == "named-scribe"
    assert first.revision_id != named.revision_id
