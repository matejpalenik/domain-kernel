"""Test coordinated review effects without persistence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from domain_kernel import (
    CaseKind,
    CaseStatus,
    DefinitionStatus,
    ReviewCaseId,
    StaleStateError,
)
from domain_kernel.review.domain.coordinated import check_group_graph, member_effects
from domain_kernel.review.domain.decisions import Accept, Reject
from domain_kernel.review.domain.models import (
    CaseDecision,
    ReviewCase,
)


def test_group_rejection_resolves_generated_members_and_releases_included_ones(
    proposal: ReviewCase,
) -> None:
    parent_id = ReviewCaseId(value="group")
    generated = replace(proposal, grouped_by_case_id=parent_id)
    included = replace(proposal, id=ReviewCaseId(value="included"), grouped_by_case_id=parent_id)
    pending = Accept(reason="Reviewed meaning.")
    parent = replace(
        proposal,
        id=parent_id,
        kind=CaseKind.CHANGE_SET,
        definitions=(),
        members=[
            CaseDecision(
                case_id=generated.id, expected_version=generated.version, decision=pending
            ),
            CaseDecision(case_id=included.id, expected_version=included.version, decision=pending),
        ],
        generated_member_case_ids=[generated.id],
        guarded_workspace_revision=1,
    )
    reject = Reject(reason="Reconsider the graph.")
    effects = member_effects(
        parent=parent,
        members=[generated, included],
        decision=reject,
    )

    assert effects[0].after.status is CaseStatus.RESOLVED
    assert effects[0].action == reject
    assert effects[1].after.status is CaseStatus.PENDING
    assert effects[1].action is None
    assert all(effect.after.grouped_by_case_id is None for effect in effects)
    assert all(effect.definitions == () for effect in effects)
    assert included.grouped_by_case_id == parent_id
    all_included = replace(parent, generated_member_case_ids=[])
    assert all(
        effect.after.status is CaseStatus.PENDING and effect.action is None
        for effect in member_effects(
            parent=all_included, members=[generated, included], decision=reject
        )
    )
    both_accepted = member_effects(parent=parent, members=[generated, included], decision=pending)
    assert all(
        effect.definitions[0].status is DefinitionStatus.APPROVED for effect in both_accepted
    )
    (issue,) = check_group_graph(scope=parent.scope, active=(), effects=both_accepted)
    assert issue.code == "contradictory_changes"
    assert all(item.definitions == proposal.definitions for item in (generated, included))

    with pytest.raises(StaleStateError):
        _ = member_effects(
            parent=parent,
            members=[replace(generated, version=2), included],
            decision=reject,
        )
