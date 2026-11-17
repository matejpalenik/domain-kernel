"""Load the scoped source cases and their durable occurrence decisions."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import uuid4

from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.review.domain.occurrences import effective_occurrences, inspect_occurrences
from domain_kernel.shared.errors import MissingCapabilityError
from domain_kernel.sources.application.citations import recorded_citation
from domain_kernel.sources.application.ports import SourceTransaction

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from domain_kernel._shared.application.persistence import TransactionManager
    from domain_kernel.review.application.ports import ReviewRepository
    from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
    from domain_kernel.review.domain.models import DecisionRecord, ReviewCase
    from domain_kernel.shared.contracts import ModelScope
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


async def check_source_citations(*, transaction: TransactionManager, case: ReviewCase) -> None:
    """Recheck the scoped evidence attached to the inspected occurrence."""
    if not isinstance(transaction, SourceTransaction):
        raise MissingCapabilityError(message="Configure exact source evidence persistence.")
    for item in case.evidence:
        _ = await recorded_citation(
            repository=transaction.sources,
            project_id=case.scope.project_id,
            expected=item,
        )


async def source_cases(
    *,
    repository: ReviewRepository,
    scope: ModelScope,
    status: CaseStatus | None = None,
) -> AsyncIterator[ReviewCase]:
    """Traverse exact source cases within the caller's transaction."""
    cursor: PageCursor | None = None
    while True:
        page = await repository.list(
            scope=scope,
            kind=CaseKind.SOURCE_ALIGNMENT,
            status=status,
            limit=100,
            cursor=cursor,
        )
        for case in page.items:
            yield case
        cursor = page.next_cursor
        if cursor is None:
            break


async def source_decisions(
    *,
    repository: ReviewRepository,
    scope: ModelScope,
) -> tuple[DecisionRecord, ...]:
    """Read occurrence effects from historical decisions and corrections."""
    decisions: list[DecisionRecord] = []
    async for case in source_cases(repository=repository, scope=scope):
        cursor: PageCursor | None = None
        while True:
            page = await repository.history(scope=scope, case_id=case.id, limit=100, cursor=cursor)
            decisions.extend(
                item for item in page.items if item.applied_changes.source_alignment_changes
            )
            cursor = page.next_cursor
            if cursor is None:
                break
    return tuple(decisions)


async def capture_correction(
    *,
    repository: ReviewRepository,
    original: ReviewCase,
    selected: Sequence[ProposalId] | None,
    reason: str,
) -> ReviewCase:
    """Capture a correction of currently effective scoped occurrence decisions."""
    if original.kind is not CaseKind.SOURCE_ALIGNMENT or original.status is not CaseStatus.RESOLVED:
        raise InvalidDecisionError(message="Reopen a resolved source occurrence decision.")
    decisions = await source_decisions(repository=repository, scope=original.scope)
    original_decisions = tuple(item for item in decisions if item.case_id == original.id)
    if not original_decisions:
        raise InvalidDecisionError(message="Reopen a case with a reviewed occurrence effect.")
    predecessor = max(original_decisions, key=lambda item: item.case_version)
    occurrences = original.proposal_ids if selected is None else selected
    captured = inspect_occurrences(
        case=original,
        selected=occurrences,
        effective=effective_occurrences(decisions=decisions),
        predecessor=predecessor.id,
    )
    active = frozenset(occurrences)
    async for pending in source_cases(
        repository=repository,
        scope=original.scope,
    ):
        if pending.status in (CaseStatus.PENDING, CaseStatus.DEFERRED) and active.intersection(
            pending.proposal_ids
        ):
            raise InvalidDecisionError(
                message="Resolve the overlapping pending occurrence correction."
            )
    return replace(
        original,
        id=ReviewCaseId(value=uuid4().hex),
        version=1,
        status=CaseStatus.PENDING,
        reason=reason,
        proposal_ids=occurrences,
        correction_of_decision_id=predecessor.id,
        correction_of_case_id=original.id,
        evidence=tuple(dict.fromkeys(item for effect in captured for item in effect.evidence)),
        grouped_by_case_id=None,
    )


async def affected_confirmations(
    *,
    repository: ReviewRepository,
    correction: ReviewCase,
) -> tuple[ReviewCase, ...]:
    """Find confirmation cases whose captured occurrences overlap the correction."""
    if correction.correction_of_case_id is None:
        return ()
    affected: list[ReviewCase] = []
    cursor: PageCursor | None = None
    while True:
        page = await repository.list(
            scope=correction.scope,
            kind=CaseKind.CONFIRMATION,
            status=None,
            limit=100,
            cursor=cursor,
        )
        affected.extend(
            case
            for case in page.items
            if case.confirmation_subject_id == correction.correction_of_case_id
            and case.status is not CaseStatus.SUPERSEDED
            and set(case.proposal_ids).intersection(correction.proposal_ids)
        )
        cursor = page.next_cursor
        if cursor is None:
            return tuple(affected)


async def reopen_affected_confirmations(
    *,
    repository: ReviewRepository,
    correction: ReviewCase,
    affected: Sequence[ReviewCase],
) -> None:
    """Preserve prior review history and reopen proof for only the changed occurrences."""
    selected = frozenset(correction.proposal_ids)
    for case in affected:
        remaining = tuple(item for item in case.proposal_ids if item not in selected)
        await repository.save(
            case=replace(
                case,
                version=case.version + 1,
                proposal_ids=remaining,
                status=case.status if remaining else CaseStatus.SUPERSEDED,
            ),
            expected_version=case.version,
        )
        await repository.add(
            case=replace(
                case,
                id=ReviewCaseId(value=uuid4().hex),
                version=1,
                status=CaseStatus.PENDING,
                confirmation_subject_id=correction.id,
                definitions=correction.definitions,
                evidence=correction.evidence,
                proposal_ids=tuple(item for item in case.proposal_ids if item in selected),
                reason="Confirm the selected occurrence after its interpretation changed.",
            )
        )
