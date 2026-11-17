"""Capture current reference choices and evaluate exact pack coverage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.reference_packs.domain.contracts import (
    COVERAGE_VALIDATOR,
    MappingRelation,
    ObligationKind,
)
from domain_kernel.shared.contracts import Issue

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.changes import ReferenceDisposition
    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.modeling.domain.snapshots import Candidate
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.review.domain.identifiers.decision_id import DecisionId
    from domain_kernel.review.domain.models import DecisionRecord


def _active(
    *,
    definitions: Sequence[Definition],
    decisions: Sequence[DecisionRecord],
    pack: ReferencePackPin,
) -> tuple[ReferenceDisposition, ...]:
    revisions = {item.id: item.revision for item in definitions}
    reviewed: list[ReferenceDisposition] = []
    superseded: set[DecisionId] = set()
    for record in decisions:
        if record.member_decision_ids:
            continue
        for change in record.applied_changes.reference_disposition_changes:
            if change.before is not None and change.before.decision_id is not None:
                superseded.add(change.before.decision_id)
            after = change.after
            if (
                after is not None
                and after.reference_pack == pack
                and after.definition_revision == revisions.get(after.definition_id)
            ):
                reviewed.append(after)
    return tuple(
        sorted(
            (item for item in reviewed if item.decision_id not in superseded),
            key=lambda item: item.definition_id.value,
        )
    )


def active_dispositions(
    *,
    definitions: Sequence[Definition],
    decisions: Sequence[DecisionRecord],
    pack: ReferencePackPin | None,
) -> tuple[ReferenceDisposition, ...]:
    """Reconstruct the deterministic current reference choices from attributed decisions."""
    if pack is None:
        return ()
    return _active(definitions=definitions, decisions=decisions, pack=pack)


def coverage_blockers(*, candidate: Candidate, pack: ReferencePack | None) -> tuple[Issue, ...]:
    """Require appropriate reviewed mappings for any required coverage obligations."""
    if pack is None:
        return ()
    covered = {
        choice.alignment.reference_id
        for choice in candidate.content.reference_dispositions
        if choice.alignment is not None
        and choice.reference_pack == pack.pin
        and choice.alignment.relation in (MappingRelation.EQUIVALENT, MappingRelation.NARROWER)
    }
    return tuple(
        Issue(
            code="reference_coverage_missing",
            path=("reference_pack", "obligations", item.id.value),
            message="Review an equivalent or narrower local meaning for each required reference.",
        )
        for item in pack.obligations
        if item.required
        and (
            item.kind is not ObligationKind.COVERAGE
            or item.validator_id != COVERAGE_VALIDATOR
            or not set(item.reference_ids) <= covered
        )
    )


def reference_context_issues(
    *,
    candidate: Candidate,
    pack: ReferencePack | None,
) -> tuple[Issue, ...]:
    """Require the exact materialized selection and current attributed references."""
    actual_pin = None if pack is None else pack.pin
    expected = active_dispositions(
        definitions=candidate.content.definitions,
        decisions=candidate.decisions,
        pack=actual_pin,
    )
    if (
        candidate.reference_pack != actual_pin
        or candidate.content.reference_dispositions != expected
    ):
        return (
            Issue(
                code="reference_context_unavailable",
                path=("reference_pack",),
                message="Materialize the exact pack and current reviewed reference dispositions.",
            ),
        )
    if pack is None:
        return ()
    known = {
        item.id
        for item in (*pack.definitions, *(item for p in pack.patterns for item in p.definitions))
    }
    if any(
        item.alignment is not None and item.alignment.reference_id not in known for item in expected
    ):
        return (
            Issue(
                code="reference_target_unavailable",
                path=("reference_pack",),
                message="Use the exact reference definitions in the selected pack.",
            ),
        )
    return tuple(pack.validate().issues)
