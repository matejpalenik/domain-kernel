"""Capture and compare exact active reference dispositions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.reference_packs.domain.contracts import ReferenceAlignment
from domain_kernel.reference_packs.domain.dispositions import active_dispositions
from domain_kernel.review.domain.decisions import ApproveLocalExtension, MapToReference
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.shared.domain.enums.reference_disposition_kind import ReferenceDispositionKind
from domain_kernel.shared.domain.value_objects.reference_disposition import ReferenceDisposition
from domain_kernel.shared.domain.value_objects.reference_disposition_change import (
    ReferenceDispositionChange,
)
from domain_kernel.shared.errors import ScopeMismatchError, StaleStateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.review.application.ports import ReviewRepository
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.identifiers.decision_id import DecisionId
    from domain_kernel.review.domain.models import DecisionRecord, ReviewCase
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


@dataclass(frozen=True, kw_only=True)
class ReviewedDisposition:
    """The exact current reference choice and the case context that captured it."""

    choice: ReferenceDisposition
    context_fingerprint: str | None


async def reviewed_dispositions(
    *,
    repository: ReviewRepository,
    definitions: Sequence[Definition],
    pack: ReferencePackPin,
) -> dict[DefinitionId, ReviewedDisposition]:
    """Find current choices and their exact case context in one paged traversal."""
    inspected = {item.id: item for item in definitions}
    if not definitions:
        return {}
    scope = definitions[0].scope
    decisions: list[DecisionRecord] = []
    contexts: dict[DecisionId | None, str | None] = {}
    for kind in (CaseKind.REFERENCE_ALIGNMENT, CaseKind.REFERENCE_PACK_CHANGE):
        token: PageCursor | None = None
        while True:
            cases = await repository.list(
                scope=scope, kind=kind, status=CaseStatus.RESOLVED, limit=100, cursor=token
            )
            for case in cases.items:
                if kind is CaseKind.REFERENCE_ALIGNMENT:
                    local = case.definitions[0]
                    if case.reference_pack != pack or inspected.get(local.id) != local:
                        continue
                else:
                    change = case.reference_pack_change
                    if change is None or change.before is None or change.before.pin != pack:
                        continue
                history = await repository.history(
                    scope=scope,
                    case_id=case.id,
                    limit=1,
                    cursor=None,
                )
                decisions.extend(history.items)
                contexts.update((item.id, case.context_fingerprint) for item in history.items)
            token = cases.next_cursor
            if token is None:
                break
    items = active_dispositions(definitions=definitions, decisions=decisions, pack=pack)
    return {
        item.definition_id: ReviewedDisposition(
            choice=item,
            context_fingerprint=contexts.get(item.decision_id),
        )
        for item in items
    }


async def prior_disposition(
    *,
    repository: ReviewRepository,
    local: Definition,
    pack: ReferencePackPin,
) -> ReferenceDisposition | None:
    """Find the most recent choice applying to the exact captured local revision."""
    reviewed = await reviewed_dispositions(repository=repository, definitions=(local,), pack=pack)
    prior = reviewed.get(local.id)
    return None if prior is None else prior.choice


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
