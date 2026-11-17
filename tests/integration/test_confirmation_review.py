"""Verify captured confirmation values and their portable public command."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    CaseStatus,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    Confirmation,
    ConfirmationMethod,
    ConfirmStatement,
    InvalidDecisionError,
    ModelKind,
    Person,
    PersonId,
    Statement,
    StatementForm,
    StatementIntent,
)
from domain_kernel._shared.domain.record_encoding import read_record, record_bytes

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import IngestedSource

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_TIME = datetime(2024, 10, 18, 9, 15, tzinfo=UTC)
_OWNER = Person(id=PersonId(value="aria"), name="Aria", role="Application owner")
_AUTHORITY = "Responsible model steward"
_REASON = "Confirm the original application-owned lookup meaning."


async def _capture(*, path: Path, at: datetime | None) -> IngestedSource:
    project = await Client(config=ClientConfiguration(base_dir=path)).create_project(
        actor="editor",
        name="clarification",
    )
    return await project.ingest_source(
        actor="recorder",
        name="field-clarification",
        source=Statement(
            text="Our lookup code points to the named provision.",
            speaker=_OWNER,
            stated_at=at,
            context="A definition used by the application.",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )


async def test_public_confirmation_retains_attribution_and_wire_payload(tmp_path: Path) -> None:
    captured = await _capture(path=tmp_path, at=_TIME)
    decision = ConfirmStatement.from_statement(
        source=captured, authority=_AUTHORITY, reason=_REASON
    )
    expected = Confirmation(
        confirmed_by=_OWNER,
        method=ConfirmationMethod.RECORDED,
        confirmed_at=_TIME,
        evidence=captured.evidence,
        recorded_by="recorder",
        recorded_at=decision.confirmation.recorded_at,
        authority=_AUTHORITY,
    )
    explicit = ConfirmStatement(confirmation=expected, reason=_REASON)
    assert explicit == decision
    assert decision.confirmation.authenticated_actor is None
    assert decision.confirmation.recorded_at > _TIME + timedelta(days=1)
    assert decision == ConfirmStatement.from_statement(
        source=captured,
        authority=_AUTHORITY,
        reason=_REASON,
    )
    payload = record_bytes(value=decision)
    assert record_bytes(value=explicit) == payload
    assert read_record(content=payload, expected=ConfirmStatement) == decision


async def test_public_confirmation_requires_original_time_and_exact_evidence(
    tmp_path: Path,
) -> None:
    captured = await _capture(path=tmp_path, at=None)
    with pytest.raises(InvalidDecisionError):
        _ = ConfirmStatement.from_statement(source=captured, authority=_AUTHORITY, reason=_REASON)
    with pytest.raises(InvalidDecisionError):
        _ = ConfirmStatement.from_statement(
            source=replace(captured, evidence=()),
            authority=_AUTHORITY,
            reason=_REASON,
        )


async def test_confirmation_reviews_separate_captured_evidence(tmp_path: Path) -> None:
    captured = await _capture(path=tmp_path, at=_TIME)
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(
        name="clarification",
    )
    model = await project.create_model(
        actor="editor",
        name="lookup",
        kind=ModelKind.PROPOSED,
        description="Review an application-owned locator.",
    )
    subject = await model.propose_definition(
        actor="editor",
        name="lookup-code",
        meaning="Local locator for the provision.",
        body=ConceptDefinition(),
        evidence=captured.evidence,
        reason="Inspect the source.",
    )
    case = await model.propose_confirmation(
        actor="editor",
        subject=subject,
        reason="Confirm the use of the local locator.",
    )
    proof = await project.ingest_source(
        actor="recorder-assistant",
        name="locator-answer",
        source=Statement(
            text="I confirm the locator is assigned by our application.",
            speaker=_OWNER,
            stated_at=_TIME + timedelta(minutes=1),
            context="Confirmation of the locator's origin.",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    decision = ConfirmStatement.from_statement(source=proof, authority=_AUTHORITY, reason=_REASON)
    forged = replace(
        decision,
        confirmation=replace(decision.confirmation, recorded_by="someone-else"),
    )
    with pytest.raises(InvalidDecisionError):
        _ = await model.preview_changes(case=case, decision=forged)
    impact = await model.preview_changes(case=case, decision=decision)
    assert impact.definition_changes == ()
    _ = await model.decide_review(case=case, decision=decision, actor="reviewer")
    history = await model.get_review_history(case_id=case.id)
    assert history.items[0].action == decision
    assert history.items[0].actor == "reviewer"
    assert (await model.get_review_case(case_id=subject.id)).status is CaseStatus.PENDING
