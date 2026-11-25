"""Test case-local review before persistence and service composition."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from domain_kernel import (
    CaseStatus,
    ConceptDefinition,
    DefinitionId,
    DefinitionStatus,
    InvalidDecisionError,
    StaleStateError,
)
from domain_kernel.review.domain.decisions import Accept, EditDefinition, Reject
from domain_kernel.review.domain.models import (
    ReviewCase,
    preview_case,
    resolve_case,
)


def test_accept_resolves_only_the_inspected_proposal(proposal: ReviewCase) -> None:
    accept = Accept(reason="The meaning matches the catalog.")
    changes = preview_case(case=proposal, decision=accept)
    assert tuple(value.status for value in changes) == (DefinitionStatus.APPROVED,)
    assert changes[0].meaning == "Physical production asset."
    resolved = resolve_case(
        case=proposal,
        decision=accept,
        actor="reviewer",
        expected_version=1,
        now=datetime.now(tz=UTC),
    )
    assert resolved.status is CaseStatus.RESOLVED
    assert resolved.version == proposal.version + 1
    assert proposal.status is CaseStatus.PENDING
    assert proposal.definitions[0].status is DefinitionStatus.PROPOSED


def test_reject_has_no_effect_and_a_stale_decision_cannot_advance(proposal: ReviewCase) -> None:
    reject = Reject(reason="The definition is out of scope.")
    assert not preview_case(case=proposal, decision=reject)
    with pytest.raises(StaleStateError):
        _ = resolve_case(
            case=proposal,
            decision=reject,
            actor="reviewer",
            expected_version=2,
            now=datetime.now(tz=UTC),
        )
    assert proposal.version == 1


def test_edit_retains_identity_and_fails_for_different_target(proposal: ReviewCase) -> None:
    edit = EditDefinition(
        definition_id=proposal.definitions[0].id,
        name="machine",
        display_name="Machine",
        body=ConceptDefinition(),
        reason="Clarify the inspected proposal.",
        meaning="An individually maintained production asset.",
    )
    changes = preview_case(case=proposal, decision=edit)
    assert changes[0].id == proposal.definitions[0].id
    assert changes[0].meaning == edit.meaning
    wrong = EditDefinition(
        definition_id=DefinitionId(value="other"),
        name=edit.name,
        display_name=edit.display_name,
        body=edit.body,
        reason=edit.reason,
        meaning=edit.meaning,
    )
    with pytest.raises(InvalidDecisionError):
        _ = preview_case(case=proposal, decision=wrong)
