"""Inspect and apply reviewed changes to one workspace's reference basis."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from uuid import uuid4

from domain_kernel._shared.domain.changes import ReferenceDispositionChange
from domain_kernel.reconciliation.application.matcher import (
    EvidenceBasedConceptMatcher,
    reference_members,
)
from domain_kernel.reference_packs.domain.changes import describe_pack_change, pack_pin
from domain_kernel.reference_packs.domain.contracts import ObligationKind
from domain_kernel.review.application.reference_alignment import reviewed_dispositions
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.review.domain.models import ReviewCase
from domain_kernel.review.domain.questions import (
    QuestionDisposition,
    RequirementKind,
    ReviewRequirement,
)
from domain_kernel.shared.errors import StaleStateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.reference_packs.domain.changes import ReferencePackChange
    from domain_kernel.reference_packs.domain.packs import ReferencePack
    from domain_kernel.review.application.ports import ReviewRepository
    from domain_kernel.review.domain.identifiers.decision_id import DecisionId
    from domain_kernel.shared.contracts import ModelScope
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


@dataclass(frozen=True, kw_only=True)
class PackReview:
    """The pack transition and currently affected review snapshots."""

    change: ReferencePackChange
    disposals: tuple[ReferenceDispositionChange, ...]
    obsolete: tuple[ReviewCase, ...]
    mixed: tuple[ReviewCase, ...]
    follow_up: tuple[ReviewCase, ...]


def _supersede(*, case: ReviewCase, decision_id: DecisionId) -> ReviewCase:
    question = case.question
    if question is not None and question.disposition is QuestionDisposition.UNRESOLVED:
        question = replace(
            question, disposition=QuestionDisposition.SUPERSEDED, decision_id=decision_id
        )
    return replace(
        case,
        version=case.version + 1,
        status=CaseStatus.SUPERSEDED,
        superseded_by_decision_id=decision_id,
        question=question,
    )


def _old_requirement(*, requirement: ReviewRequirement, pin: ReferencePackPin) -> bool:
    return requirement.kind is RequirementKind.REFERENCE_PACK and requirement.reference_pack == pin


def _generated_for(*, case: ReviewCase, pin: ReferencePackPin) -> bool:
    return (
        case.reference_pack == pin
        and case.kind is CaseKind.REFERENCE_ALIGNMENT
        and (case.reconciliation_id is not None or case.generated_by_pack_change_id is not None)
    )


async def _obsolete(
    *, reviews: ReviewRepository, scope: ModelScope, pin: ReferencePackPin
) -> tuple[tuple[ReviewCase, ...], tuple[ReviewCase, ...]]:
    superseded: list[ReviewCase] = []
    mixed: list[ReviewCase] = []
    for status in (CaseStatus.PENDING, CaseStatus.DEFERRED):
        cursor: PageCursor | None = None
        while True:
            page = await reviews.list(
                scope=scope, kind=None, status=status, limit=100, cursor=cursor
            )
            for case in page.items:
                old = tuple(
                    item
                    for item in case.requirements
                    if _old_requirement(requirement=item, pin=pin)
                )
                if case.requirements and len(old) != len(case.requirements):
                    if old:
                        mixed.append(case)
                elif _generated_for(case=case, pin=pin) or (old and case.kind is CaseKind.QUESTION):
                    superseded.append(case)
            cursor = page.next_cursor
            if cursor is None:
                break
    return tuple(superseded), tuple(mixed)


def _follow_up(
    *, pack: ReferencePack, active: Sequence[Definition], previous: set[DefinitionId]
) -> tuple[ReviewCase, ...]:
    members = reference_members(pack=pack)
    matcher = EvidenceBasedConceptMatcher()
    cases: list[ReviewCase] = []
    for local in active:
        suggestions = {item.target.id for item in matcher.reference(local=local, members=members)}
        obligations = tuple(
            item
            for item in pack.obligations
            if item.kind is ObligationKind.COVERAGE and suggestions.intersection(item.reference_ids)
        )
        if not (
            any(item.required for item in obligations) or (suggestions and local.id in previous)
        ):
            continue
        cases.append(
            ReviewCase(
                id=ReviewCaseId(value=uuid4().hex),
                scope=local.scope,
                kind=CaseKind.REFERENCE_ALIGNMENT,
                status=CaseStatus.PENDING,
                version=1,
                definitions=(local,),
                reason="Review this local meaning against the newly selected pack.",
                reference_pack=pack.pin,
                requirements=tuple(
                    ReviewRequirement(
                        kind=RequirementKind.REFERENCE_PACK,
                        code="reference_coverage",
                        required=obligation.required,
                        reference_pack=pack.pin,
                        obligation_id=obligation.id,
                    )
                    for obligation in obligations
                ),
            )
        )
    return tuple(cases)


async def inspect_pack_review(
    *,
    reviews: ReviewRepository,
    scope: ModelScope,
    active: Sequence[Definition],
    before: ReferencePack | None,
    after: ReferencePack | None,
) -> PackReview:
    """Inspect old dispositions and applicable follow-up for the exact transition."""
    old_pin = pack_pin(pack=before)
    if old_pin is None:
        dispositions, obsolete, mixed = {}, (), ()
    else:
        dispositions = await reviewed_dispositions(
            repository=reviews, definitions=active, pack=old_pin
        )
        obsolete, mixed = await _obsolete(reviews=reviews, scope=scope, pin=old_pin)
    follow_up = (
        () if after is None else _follow_up(pack=after, active=active, previous=set(dispositions))
    )
    affected = set(dispositions)
    affected.update(case.definitions[0].id for case in follow_up)
    affected.update(item.id for case in obsolete for item in case.definitions)
    affected.update(item.id for case in mixed for item in case.definitions)
    return PackReview(
        change=describe_pack_change(
            before=before,
            after=after,
            definitions=tuple(item.id for item in active if item.id in affected),
            superseded=tuple(item.id for item in obsolete),
        ),
        disposals=tuple(
            ReferenceDispositionChange(before=item.choice, after=None)
            for item in dispositions.values()
        ),
        obsolete=obsolete,
        mixed=mixed,
        follow_up=follow_up,
    )


async def apply_pack_requirements(
    *,
    reviews: ReviewRepository,
    effects: PackReview,
    decision_id: DecisionId,
    case_id: ReviewCaseId,
) -> tuple[ReviewCase, ...]:
    """Persist only the affected requirement transitions inside the accepting transaction."""
    updated: list[ReviewCase] = []
    current = pack_pin(pack=effects.change.before)
    for case in effects.obsolete:
        superseded = _supersede(case=case, decision_id=decision_id)
        await reviews.save(case=superseded, expected_version=case.version)
        updated.append(superseded)
    if current is not None:
        for case in effects.mixed:
            requirements = tuple(
                item
                for item in case.requirements
                if not _old_requirement(requirement=item, pin=current)
            )
            question = case.question
            if question is not None and any(
                item.obligation_id == question.obligation_id
                for item in case.requirements
                if _old_requirement(requirement=item, pin=current)
            ):
                question = None
            changed = replace(
                case, requirements=requirements, question=question, version=case.version + 1
            )
            await reviews.save(case=changed, expected_version=case.version)
            updated.append(changed)
    for case in effects.follow_up:
        generated = replace(case, generated_by_pack_change_id=case_id)
        await reviews.add(case=generated)
        updated.append(generated)
    return tuple(updated)


def require_current_pack_review(
    *, case: ReviewCase, revision: int, current: ReferencePack | None
) -> ReferencePackChange:
    """Require the exact inspected working selection and post-proposal revision."""
    transition = case.reference_pack_change
    if (
        transition is None
        or case.guarded_workspace_revision != revision
        or transition.before != current
    ):
        raise StaleStateError(message="Inspect a new pack change against the current workspace.")
    return transition
