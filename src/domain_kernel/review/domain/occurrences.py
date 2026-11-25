"""Compute attributed source effects from inspected review state."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from domain_kernel.review.domain.decisions import Accept, EditDefinition, Exclude, MapToDefinition
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.shared.domain.enums.source_disposition import SourceDisposition
from domain_kernel.shared.domain.value_objects.source_alignment import SourceAlignment
from domain_kernel.shared.domain.value_objects.source_alignment_change import SourceAlignmentChange
from domain_kernel.shared.errors import StaleStateError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.identifiers.decision_id import DecisionId
    from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
    from domain_kernel.review.domain.models import DecisionRecord, ReviewCase
    from domain_kernel.shared.domain.entities.definition import Definition


def effective_occurrences(
    *, decisions: Sequence[DecisionRecord]
) -> dict[ProposalId, SourceAlignment]:
    """Apply recorded supersession to individual occurrence effects."""
    effective: dict[ProposalId, SourceAlignment] = {}
    superseded: set[tuple[ProposalId, DecisionId | None]] = set()
    proposed: list[SourceAlignment] = []
    for record in decisions:
        if record.member_decision_ids:
            continue
        for change in record.applied_changes.source_alignment_changes:
            if change.before is not None:
                superseded.add((change.before.proposal_id, change.before.decision_id))
            if change.after is not None:
                proposed.append(change.after)
    for item in proposed:
        if (item.proposal_id, item.decision_id) in superseded:
            continue
        prior = effective.setdefault(item.proposal_id, item)
        if prior != item:
            raise StaleStateError(message="Inspect the conflicting source occurrence decisions.")
    return effective


def alignments_at_revision(
    *, decisions: Sequence[DecisionRecord], definitions: Sequence[Definition]
) -> tuple[SourceAlignment, ...]:
    """Mark captured choices stale when their reviewed local revisions change."""
    revisions = {item.id: item.revision for item in definitions}
    effective = effective_occurrences(decisions=decisions)
    return tuple(
        replace(item, disposition=SourceDisposition.STALE)
        if item.disposition is SourceDisposition.MAPPED
        and item.definition_id is not None
        and revisions.get(item.definition_id) != item.definition_revision
        else item
        for item in sorted(effective.values(), key=lambda alignment: alignment.proposal_id.value)
    )


def inspect_occurrences(
    *,
    case: ReviewCase,
    selected: Sequence[ProposalId],
    effective: Mapping[ProposalId, SourceAlignment],
    predecessor: DecisionId,
) -> tuple[SourceAlignment, ...]:
    """Find each selected effect still attributable to the earlier decision."""
    if (
        not selected
        or len(set(selected)) != len(selected)
        or not set(selected) <= set(case.proposal_ids)
    ):
        raise ValueError("Select distinct occurrences from the inspected source review.")
    state: list[SourceAlignment] = []
    for identity in selected:
        current = effective.get(identity)
        if current is None or current.decision_id != predecessor:
            raise StaleStateError(message="Reopen the current effective occurrence decision.")
        state.append(current)
    return tuple(state)


def source_effects(
    *,
    case: ReviewCase,
    decision: ReviewAction,
    effective: Mapping[ProposalId, SourceAlignment],
) -> tuple[SourceAlignmentChange, ...]:
    """Preview exactly the selected occurrence changes without modifying definitions."""
    if case.kind is not CaseKind.SOURCE_ALIGNMENT or not isinstance(
        decision, (MapToDefinition, Exclude, Accept, EditDefinition)
    ):
        return ()
    if case.correction_of_decision_id is not None:
        _ = inspect_occurrences(
            case=case,
            selected=case.proposal_ids,
            effective=effective,
            predecessor=case.correction_of_decision_id,
        )
    elif any(identity in effective for identity in case.proposal_ids):
        raise StaleStateError(
            message="Reopen the existing interpretation before correcting its occurrences."
        )
    fingerprint = case.context_fingerprint
    if fingerprint is None:
        raise InvalidDecisionError(message="Inspect the captured source interpretation context.")
    target = case.definitions[0] if isinstance(decision, (Accept, EditDefinition)) else None
    if isinstance(decision, MapToDefinition):
        target = decision.definition
    return tuple(
        SourceAlignmentChange(
            before=effective.get(identity),
            after=SourceAlignment(
                proposal_id=identity,
                definition_id=None if target is None else target.id,
                definition_revision=None if target is None else target.revision,
                disposition=SourceDisposition.EXCLUDED
                if target is None
                else SourceDisposition.MAPPED,
                decision_id=None,
                rationale=decision.reason,
                context_fingerprint=fingerprint,
                evidence=case.evidence
                if identity not in effective
                else effective[identity].evidence,
            ),
        )
        for identity in case.proposal_ids
    )
