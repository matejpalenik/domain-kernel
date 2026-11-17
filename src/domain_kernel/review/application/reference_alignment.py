"""Capture and compare exact active reference dispositions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel._shared.domain.changes import (
    ReferenceDisposition,
    ReferenceDispositionChange,
    ReferenceDispositionKind,
)
from domain_kernel.reference_packs.domain.contracts import ReferenceAlignment
from domain_kernel.reference_packs.domain.dispositions import active_dispositions
from domain_kernel.review.domain.decisions import ApproveLocalExtension, MapToReference
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.shared.errors import ScopeMismatchError, StaleStateError

if TYPE_CHECKING:
    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.review.application.ports import ReviewRepository
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.models import DecisionRecord, ReviewCase
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


async def prior_disposition(
    *,
    repository: ReviewRepository,
    local: Definition,
    pack: ReferencePackPin,
) -> ReferenceDisposition | None:
    """Find the most recent choice applying to the exact captured local revision."""
    token: PageCursor | None = None
    decisions: list[DecisionRecord] = []
    while True:
        cases = await repository.list(
            scope=local.scope,
            kind=CaseKind.REFERENCE_ALIGNMENT,
            status=CaseStatus.RESOLVED,
            limit=100,
            cursor=token,
        )
        for case in cases.items:
            if case.reference_pack == pack and case.definitions == (local,):
                history = await repository.history(
                    scope=local.scope,
                    case_id=case.id,
                    limit=1,
                    cursor=None,
                )
                decisions.extend(history.items)
        token = cases.next_cursor
        if token is None:
            break
    items = active_dispositions(definitions=(local,), decisions=decisions, pack=pack)
    return items[0] if items else None


def inspect_alignment(
    *,
    case: ReviewCase,
    decision: ReviewAction,
    pack: ReferencePack,
    previous: ReferenceDisposition | None,
) -> tuple[ReferenceDispositionChange, ...]:
    """Verify the exact capture and return the proposed reference disposition."""
    if pack.pin != case.reference_pack or case.reference_before != previous:
        raise StaleStateError(
            message="Inspect a fresh case against the selected pack and prior decision"
        )
    members = {
        item.id: item
        for item in (*pack.definitions, *(m for p in pack.patterns for m in p.definitions))
    }
    if isinstance(decision, MapToReference):
        if (
            decision.reference_pack != pack.pin
            or decision.reference_definition.reference_pack != pack.pin
        ):
            raise ScopeMismatchError
        stored = members.get(decision.reference_id)
        if stored != decision.reference_definition:
            raise StaleStateError(
                message="Reload the exact reference definition from the selected pack"
            )
        relation = ReferenceAlignment(
            reference_id=decision.reference_id,
            reference_pack=pack.pin,
            relation=decision.relation,
            reason=decision.reason,
        )
        disposition = ReferenceDispositionKind.MAPPED
    elif isinstance(decision, ApproveLocalExtension):
        if any(
            item.reference_pack != pack.pin or item.reference_id not in members
            for item in decision.relationships
        ):
            raise InvalidDecisionError(
                message="Review extension relationships in the exact selected pack"
            )
        relation = None
        disposition = ReferenceDispositionKind.LOCAL_EXTENSION
    else:
        return ()

    local = case.definitions[0]
    return (
        ReferenceDispositionChange(
            before=previous,
            after=ReferenceDisposition(
                definition_id=local.id,
                definition_revision=local.revision,
                reference_pack=pack.pin,
                disposition=disposition,
                alignment=relation,
                decision_id=None,
                rationale=decision.reason,
            ),
        ),
    )
