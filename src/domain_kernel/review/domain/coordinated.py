"""Pure coordinated review policy over captured cases and their explicit actions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.lifecycle import check_definition_changes, definition_change
from domain_kernel.review.domain.decisions import Accept, Reject
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.review.domain.models import preview_case
from domain_kernel.shared.errors import StaleStateError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel._shared.domain.changes import (
        ReferenceDispositionChange,
        SourceAlignmentChange,
    )
    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel._shared.domain.ontology_closure import OntologyClosure
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.models import ReviewCase
    from domain_kernel.shared.contracts import Issue, ModelScope, PinnedDefinitionReference


@dataclass(frozen=True, kw_only=True)
class MemberEffect:
    """One member's immutable transition and any applied action."""

    before: ReviewCase
    after: ReviewCase
    action: ReviewAction | None
    definitions: tuple[Definition, ...]
    source_changes: tuple[SourceAlignmentChange, ...] = ()
    reference_changes: tuple[ReferenceDispositionChange, ...] = ()


def member_effects(
    *,
    parent: ReviewCase,
    members: Sequence[ReviewCase],
    decision: ReviewAction,
) -> tuple[MemberEffect, ...]:
    """Resolve generated members and release included cases under the parent rules."""
    if parent.kind is not CaseKind.CHANGE_SET or parent.status is not CaseStatus.PENDING:
        raise InvalidDecisionError(message="Inspect a pending coordinated review")
    if type(decision) not in (Accept, Reject):
        raise InvalidDecisionError(message="Accept or reject the inspected group as a whole")
    if len(parent.members) != len(members):
        raise StaleStateError(message="Reload all reserved members of the coordinated case")
    result: list[MemberEffect] = []
    for selected, member in zip(parent.members, members, strict=True):
        if (
            member.scope != parent.scope
            or member.grouped_by_case_id != parent.id
            or member.id != selected.case_id
            or member.version != selected.expected_version
            or member.status is not CaseStatus.PENDING
            or member.kind is CaseKind.CHANGE_SET
        ):
            raise StaleStateError(message="Reload the inspected member cases and their versions")
        released = replace(member, grouped_by_case_id=None)
        if isinstance(decision, Reject) and member.id not in parent.generated_member_case_ids:
            result.append(
                MemberEffect(
                    before=member,
                    after=replace(released, version=member.version + 1),
                    action=None,
                    definitions=(),
                )
            )
            continue
        action = decision if isinstance(decision, Reject) else selected.decision
        result.append(
            MemberEffect(
                before=member,
                after=replace(released, status=CaseStatus.RESOLVED, version=member.version + 1),
                action=action,
                definitions=preview_case(case=released, decision=action),
            )
        )
    return tuple(result)


def check_group_graph(
    *,
    scope: ModelScope,
    active: Sequence[Definition],
    effects: Sequence[MemberEffect],
    dependencies: Mapping[PinnedDefinitionReference, Definition] | None = None,
    ontologies: Sequence[OntologyClosure] = (),
) -> tuple[Issue, ...]:
    """Validate the entire prospective graph from the captured member effects."""
    changes = tuple(
        definition_change(before=effect.before.before_definition, after=definition)
        for effect in effects
        for definition in effect.definitions
    )
    if not changes:
        return ()
    return check_definition_changes(
        scope=scope,
        active=active,
        changes=changes,
        dependencies=dependencies,
        ontologies=ontologies,
    )
