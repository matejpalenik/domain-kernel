"""Submit and resolve a coordinated graph in one application transaction."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel.modeling.domain.dependencies import dependency_definitions
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.reference_packs.application.adoption import build_adoption_plan, inspect_pattern
from domain_kernel.reference_packs.domain.contracts import DefinitionBinding, Pattern
from domain_kernel.review.application.dependency_upgrade import capture_upgrade, inspect_upgrade
from domain_kernel.review.application.lifecycle import check_inspected, lifecycle_case
from domain_kernel.review.application.ontology_resources import review_ontology_resources
from domain_kernel.review.application.reference_alignment import (
    inspect_alignment,
    prior_disposition,
)
from domain_kernel.review.application.source_review import (
    affected_confirmations,
    capture_correction,
    check_source_citations,
    reopen_affected_confirmations,
    source_decisions,
)
from domain_kernel.review.domain.coordinated import check_group_graph, member_effects
from domain_kernel.review.domain.decisions import Accept, MapToDefinition, Reject
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.review.domain.models import (
    CaseDecision,
    DecisionRecord,
    ReviewCase,
    ReviewImpact,
    ReviewReceipt,
    preview_case,
)
from domain_kernel.review.domain.occurrences import effective_occurrences, source_effects
from domain_kernel.shared.application.persistence import Invocation, Lease, OperationOutcome
from domain_kernel.shared.contracts import PinnedDefinitionReference
from domain_kernel.shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel.shared.domain.authoring import (
    CorrectMapping,
    CreateDefinition,
    IncludeCase,
    MapToPlannedDefinition,
    ModelChangePlan,
    RestoreDefinition,
    ReviseDefinition,
)
from domain_kernel.shared.domain.changes import (
    ChangeSet,
    ComparisonKind,
    Compatibility,
    DefinitionChange,
)
from domain_kernel.shared.domain.lifecycle import check_definition_changes, definition_change
from domain_kernel.shared.domain.record_encoding import record_bytes, record_value
from domain_kernel.shared.domain.shape_graph import shape_references
from domain_kernel.shared.errors import MissingCapabilityError, StaleStateError
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.application.dependencies import PublishedDependencies
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.reference_packs.application.selection_ports import SelectedPacks
    from domain_kernel.review.application.ports import DefinitionRepository, ReviewRepository
    from domain_kernel.review.domain.coordinated import MemberEffect
    from domain_kernel.review.domain.decisions import ContentChangeAction, ReviewAction
    from domain_kernel.shared.application.persistence import (
        AuditRepository,
        IdempotencyRepository,
        TransactionManager,
        WorkspaceRevisions,
    )
    from domain_kernel.shared.contracts import DefinitionReference, ModelScope
    from domain_kernel.shared.domain.authoring import LifecycleOperation, PlannedOperation
    from domain_kernel.shared.domain.definitions import Definition


def _resource(
    *,
    identity: ReviewCaseId | ChangePlanId | DecisionId | DefinitionId,
    revision: int | None,
    value: object,
) -> AuditResource:
    return AuditResource(
        resource_id=identity,
        revision=revision,
        content_hash=hash_bytes(content=record_bytes(value=value)),
    )


@final
class CoordinatedReview:
    """Compose one short transaction for group reservation, preview or final decision."""

    def __init__(  # noqa: PLR0913 - Inject each used capability directly.
        self,
        *,
        scope: ModelScope,
        definitions: DefinitionRepository,
        reviews: ReviewRepository,
        audit: AuditRepository,
        operations: IdempotencyRepository,
        revisions: WorkspaceRevisions,
        transaction: TransactionManager,
        resolver: PublishedDependencies | None = None,
        packs: SelectedPacks | None = None,
    ) -> None:
        """Bind the operation's repositories."""
        self._scope = scope
        self._definitions = definitions
        self._reviews = reviews
        self._audit = audit
        self._operations = operations
        self._revisions = revisions
        self._transaction = transaction
        self._resolver = resolver
        self._packs = packs

    async def submit_plan(
        self,
        *,
        plan: ModelChangePlan,
        actor: str,
        idempotency_key: str | None,
    ) -> ReviewCase:
        """Bind the plan ID to exact content independently of a caller retry key."""
        if plan.pattern_adoption is not None:
            raise InvalidDecisionError(message="Submit selected patterns through propose_pattern")
        if plan.scope != self._scope:
            raise InvalidDecisionError(message="Use a plan from this exact workspace")
        intent = record_value(value=plan)
        primary = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="propose_plan",
            actor=actor,
            key=plan.id.value,
            intent=intent,
        )
        request = (
            None
            if idempotency_key is None
            else Invocation.resolve(
                project_id=self._scope.project_id,
                model_id=self._scope.model_id,
                operation="plan_request",
                actor=actor,
                key=idempotency_key,
                intent=intent,
            )
        )
        async with self._transaction.begin():
            owner = uuid4().hex
            claimed = await self._operations.claim(invocation=primary, owner=owner)
            secondary = (
                None
                if request is None
                else await self._operations.claim(invocation=request, owner=owner)
            )
            if isinstance(claimed, OperationOutcome):
                outcome = claimed
                parent = await self._parent_result(outcome=outcome)
            else:
                parent = await self._submit(plan=plan, actor=actor)
                outcome = OperationOutcome(
                    resource_kind="coordinated_case", resource_id=parent.id.value
                )
                await self._operations.complete(invocation=primary, lease=claimed, outcome=outcome)
            if request is not None and isinstance(secondary, Lease):
                await self._operations.complete(
                    invocation=request, lease=secondary, outcome=outcome
                )
            elif isinstance(secondary, OperationOutcome) and secondary != outcome:
                raise InvalidDecisionError(
                    message="The stored coordinated plan outcome is inconsistent"
                )
            return parent

    async def adopt_pattern(  # noqa: PLR0913 - Complete explicit adoption request.
        self,
        *,
        actor: str,
        pattern: Pattern,
        bindings: Sequence[DefinitionBinding],
        reason: str,
        idempotency_key: str | None,
        packs: SelectedPacks,
    ) -> ReviewCase:
        """Resolve review intent before minting or reserving any local identities."""
        RuntimeTypeValidation.require_exact(
            value=pattern, expected=Pattern, field="Selected pattern"
        )
        TextValidation.require_text(value=reason, field="Adoption reason")
        selected = SequenceValidation.snapshot_sequence(
            items=bindings,
            item_type=DefinitionBinding,
            field="Pattern bindings",
        )
        invocation = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="propose_pattern",
            actor=actor,
            key=idempotency_key,
            intent=record_value(value=(pattern.reference_pack, pattern, selected, reason)),
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=invocation, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                return await self._parent_result(outcome=claim)
            stored = inspect_pattern(pack=await packs.get(scope=self._scope), requested=pattern)
            plan = await build_adoption_plan(
                scope=self._scope,
                revision=await self._revisions.revision(scope=self._scope),
                pattern=stored,
                bindings=selected,
                reason=reason,
                repository=self._definitions,
            )
            parent = await self._submit(plan=plan, actor=actor)
            await self._operations.complete(
                invocation=invocation,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="coordinated_case", resource_id=parent.id.value
                ),
            )
            return parent

    async def group_cases(
        self,
        *,
        actor: str,
        decisions: Sequence[CaseDecision],
        expected_workspace_revision: int,
        reason: str,
        idempotency_key: str | None,
    ) -> ReviewCase:
        """Reserve existing inspected members without introducing generated cases."""
        selected = SequenceValidation.snapshot_sequence(
            items=decisions, item_type=CaseDecision, field="Selected cases"
        )
        operations = tuple(
            IncludeCase(
                case_id=item.case_id,
                expected_version=item.expected_version,
                decision=item.decision,
            )
            for item in selected
        )
        plan = ModelChangePlan(
            id=ChangePlanId(value=uuid4().hex),
            scope=self._scope,
            expected_workspace_revision=expected_workspace_revision,
            reason=reason,
            bindings=(),
            operations=operations,
        )
        invocation = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="group_cases",
            actor=actor,
            key=idempotency_key,
            intent=record_value(value=(expected_workspace_revision, reason, operations)),
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=invocation, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                return await self._parent_result(outcome=claim)
            parent = await self._submit(plan=plan, actor=actor)
            await self._operations.complete(
                invocation=invocation,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="coordinated_case",
                    resource_id=parent.id.value,
                ),
            )
            return parent

    async def _parent_result(self, *, outcome: OperationOutcome) -> ReviewCase:
        if outcome.resource_kind != "coordinated_case":
            raise InvalidDecisionError(message="The stored coordinated result is invalid")
        return await self._reviews.get(
            scope=self._scope,
            case_id=ReviewCaseId(value=outcome.resource_id),
            version=None,
        )

    async def _validate_plan_base(self, *, plan: ModelChangePlan) -> int:
        revision = await self._revisions.revision(scope=self._scope)
        if revision != plan.expected_workspace_revision:
            raise StaleStateError(message="Reload the workspace and inspect a new plan")
        pending_pack = await self._reviews.list(
            scope=self._scope,
            kind=CaseKind.REFERENCE_PACK_CHANGE,
            status=CaseStatus.PENDING,
            limit=1,
            cursor=None,
        )
        if pending_pack.items:
            raise InvalidDecisionError(
                message="Resolve or reject the pending reference-pack change."
            )
        for binding in plan.bindings:
            current = await self._definitions.get(
                scope=self._scope,
                name=None,
                definition_id=binding.id,
                revision=None,
            )
            if current != binding:
                raise StaleStateError(message="Reload the plan's inspected definition bindings")
        if plan.dependency_change is not None:
            pending = await self._reviews.list(
                scope=self._scope,
                kind=CaseKind.CHANGE_SET,
                status=CaseStatus.PENDING,
                limit=1,
                cursor=None,
            )
            if pending.items:
                raise InvalidDecisionError(
                    message="Resolve or reject the currently reserved coordinated cases first",
                )
        return revision

    async def _submit(self, *, plan: ModelChangePlan, actor: str) -> ReviewCase:
        revision = await self._validate_plan_base(plan=plan)
        active = await self._definitions.active(scope=self._scope)
        dependency_change, automatic = await capture_upgrade(
            plan=plan,
            active=active,
            resolver=self._resolver,
        )
        parent_id = ReviewCaseId(value=uuid4().hex)
        allowed = {
            *(bound.id for bound in plan.bindings),
            *(item.definition_id for item in plan.operations if isinstance(item, CreateDefinition)),
        }
        members, actions, generated = await self._capture_members(
            operations=(*plan.operations, *automatic),
            parent_id=parent_id,
            allowed=allowed,
        )
        parent = ReviewCase(
            id=parent_id,
            scope=self._scope,
            kind=CaseKind.CHANGE_SET,
            status=CaseStatus.PENDING,
            version=1,
            definitions=(),
            reason=plan.reason,
            change_plan=plan,
            dependency_change=dependency_change,
            members=actions,
            generated_member_case_ids=generated,
            guarded_workspace_revision=revision + 1,
        )
        effects = member_effects(
            parent=parent, members=members, decision=Accept(reason=plan.reason)
        )
        _ = await self._mapping_effects(effects=effects)
        if dependency_change is None:
            archives = (
                ()
                if self._resolver is None
                else await self._resolver.materialize(
                    scope=self._scope,
                    pins=await self._resolver.selected(scope=self._scope),
                )
            )
            issues = check_group_graph(
                scope=self._scope,
                active=active,
                effects=effects,
                dependencies=dependency_definitions(scope=self._scope, bundles=archives),
                ontologies=await review_ontology_resources(
                    scope=self._scope,
                    selected=self._packs,
                    dependencies=archives,
                ),
            )
            if issues:
                raise InvalidDecisionError(
                    message="Resolve the combined plan's shape references",
                    issues=issues,
                )
        await self._reviews.add(case=parent)
        for member in members:
            if member.id in generated:
                if member.kind is CaseKind.PROPOSAL:
                    await self._definitions.reserve(definition=member.definitions[0])
                await self._reviews.add(case=member)
            else:
                await self._reviews.save(case=member, expected_version=member.version - 1)
        await self._revisions.advance(scope=self._scope, expected_revision=revision)
        await self._audit.append(
            record=AuditRecord(
                id=AuditId(value=uuid4().hex),
                project_id=self._scope.project_id,
                model_id=self._scope.model_id,
                action=AuditAction.PROPOSE_CHANGE,
                outcome=AuditOutcome.SUCCEEDED,
                actor=actor,
                recorded_at=datetime.now(tz=UTC),
                reason=plan.reason,
                before=(),
                after=(
                    _resource(identity=plan.id, revision=None, value=plan),
                    _resource(identity=parent.id, revision=parent.version, value=parent),
                    *(
                        _resource(identity=member.id, revision=member.version, value=member)
                        for member in members
                    ),
                ),
            )
        )
        return parent

    async def _capture_members(
        self,
        *,
        operations: Sequence[PlannedOperation],
        parent_id: ReviewCaseId,
        allowed: set[DefinitionId],
    ) -> tuple[tuple[ReviewCase, ...], tuple[CaseDecision, ...], tuple[ReviewCaseId, ...]]:
        members: list[ReviewCase] = []
        actions: list[ContentChangeAction | Reject | MapToPlannedDefinition] = []
        generated: list[ReviewCaseId] = []
        planned: dict[DefinitionId, Definition] = {}
        for item in operations:
            if isinstance(item, IncludeCase):
                member = await self._reserve_existing(item=item, parent_id=parent_id)
                action = item.decision
            elif isinstance(item, CorrectMapping):
                member = await self._capture_mapping_correction(item=item, parent_id=parent_id)
                action = item.decision
                generated.append(member.id)
            else:
                member = await self._capture_generated(
                    item=item, parent_id=parent_id, allowed=allowed
                )
                action = Accept(reason=item.reason)
                if isinstance(item, (CreateDefinition, ReviseDefinition, RestoreDefinition)):
                    (prospective,) = preview_case(
                        case=replace(member, grouped_by_case_id=None),
                        decision=action,
                    )
                    planned[prospective.id] = prospective
                generated.append(member.id)
            members.append(member)
            actions.append(action)
        decisions = tuple(
            CaseDecision(
                case_id=member.id,
                expected_version=member.version,
                decision=self._resolve_mapping(action=action, planned=planned),
            )
            for member, action in zip(members, actions, strict=True)
        )
        return tuple(members), decisions, tuple(generated)

    @staticmethod
    def _resolve_mapping(
        *,
        action: ContentChangeAction | Reject | MapToPlannedDefinition,
        planned: dict[DefinitionId, Definition],
    ) -> ContentChangeAction | Reject:
        if not isinstance(action, MapToPlannedDefinition):
            return action
        local = planned.get(action.definition_id)
        if local is None:
            raise InvalidDecisionError(
                message="Select a definition created, revised or restored by this plan."
            )
        return MapToDefinition(definition=local, reason=action.reason)

    async def _capture_mapping_correction(
        self,
        *,
        item: CorrectMapping,
        parent_id: ReviewCaseId,
    ) -> ReviewCase:
        original = await self._reviews.get(scope=self._scope, case_id=item.case_id, version=None)
        if original.version != item.expected_version:
            raise StaleStateError(
                message="Inspect the current mapping before planning its correction."
            )
        if original.kind is CaseKind.SOURCE_ALIGNMENT:
            case = await capture_correction(
                repository=self._reviews,
                original=original,
                selected=item.proposal_ids,
                reason=item.reason,
            )
        else:
            case = await self._capture_reference_correction(original=original, item=item)
        return replace(case, grouped_by_case_id=parent_id)

    async def _capture_reference_correction(
        self,
        *,
        original: ReviewCase,
        item: CorrectMapping,
    ) -> ReviewCase:
        pack = None if self._packs is None else await self._packs.get(scope=self._scope)
        if (
            original.kind is not CaseKind.REFERENCE_ALIGNMENT
            or original.status is not CaseStatus.RESOLVED
            or item.proposal_ids is not None
            or pack is None
            or pack.pin != original.reference_pack
        ):
            raise InvalidDecisionError(
                message="Inspect a resolved disposition in the selected exact pack."
            )
        local = original.definitions[0]
        await check_inspected(repository=self._definitions, before=local)
        prior = await prior_disposition(repository=self._reviews, local=local, pack=pack.pin)
        history = await self._reviews.history(
            scope=self._scope,
            case_id=original.id,
            limit=1,
            cursor=None,
        )
        if prior is None or not history.items or prior.decision_id != history.items[0].id:
            raise StaleStateError(message="Select the current reference disposition.")
        return replace(
            original,
            id=ReviewCaseId(value=uuid4().hex),
            version=1,
            status=CaseStatus.PENDING,
            reference_before=prior,
            grouped_by_case_id=None,
            reason=item.reason,
        )

    async def _mapping_effects(
        self,
        *,
        effects: Sequence[MemberEffect],
    ) -> tuple[MemberEffect, ...]:
        proposed = {item.id: item for effect in effects for item in effect.definitions}
        effective = None
        prepared: list[MemberEffect] = []
        for effect in effects:
            case = effect.before
            action = effect.action
            if action is None or isinstance(action, Reject):
                prepared.append(effect)
                continue
            if case.kind is CaseKind.SOURCE_ALIGNMENT:
                if effective is None:
                    effective = effective_occurrences(
                        decisions=await source_decisions(
                            repository=self._reviews, scope=self._scope
                        ),
                    )
                if isinstance(action, MapToDefinition):
                    await self._check_mapping_target(case=case, action=action, proposed=proposed)
                await check_source_citations(transaction=self._transaction, case=case)
                prepared.append(
                    replace(
                        effect,
                        source_changes=source_effects(
                            case=case, decision=action, effective=effective
                        ),
                    )
                )
            elif case.kind is CaseKind.REFERENCE_ALIGNMENT:
                pack = None if self._packs is None else await self._packs.get(scope=self._scope)
                if pack is None:
                    raise MissingCapabilityError(
                        message="Select the exact reference pack for review."
                    )
                local = case.definitions[0]
                if local.id in proposed:
                    raise InvalidDecisionError(
                        message="Inspect the reference mapping after the local revision."
                    )
                await check_inspected(repository=self._definitions, before=local)
                prior = await prior_disposition(
                    repository=self._reviews, local=local, pack=pack.pin
                )
                prepared.append(
                    replace(
                        effect,
                        reference_changes=inspect_alignment(
                            case=case, decision=action, pack=pack, previous=prior
                        ),
                    )
                )
            else:
                prepared.append(effect)
        return tuple(prepared)

    async def _check_mapping_target(
        self,
        *,
        case: ReviewCase,
        action: MapToDefinition,
        proposed: dict[DefinitionId, Definition],
    ) -> None:
        target = action.definition
        final = proposed.get(target.id)
        if target.scope != self._scope or target.body.kind is not case.definitions[0].body.kind:
            raise InvalidDecisionError(
                message="Select a compatible local meaning in this workspace."
            )
        if final is None:
            await check_inspected(repository=self._definitions, before=target)
        elif final != target or final.status is not DefinitionStatus.APPROVED:
            raise StaleStateError(message="Inspect the final planned local meaning.")

    async def _capture_generated(
        self,
        *,
        item: CreateDefinition | LifecycleOperation,
        parent_id: ReviewCaseId,
        allowed: set[DefinitionId],
    ) -> ReviewCase:
        inherited: set[DefinitionReference] = set()
        if isinstance(item, CreateDefinition):
            member = ReviewCase(
                id=ReviewCaseId(value=uuid4().hex),
                scope=self._scope,
                kind=CaseKind.PROPOSAL,
                status=CaseStatus.PENDING,
                version=1,
                definitions=(item.draft(scope=self._scope),),
                reason=item.reason,
                grouped_by_case_id=parent_id,
            )
        else:
            await check_inspected(repository=self._definitions, before=item.before)
            member = lifecycle_case(operation=item, grouped_by_case_id=parent_id)
            inherited = {edge.target for edge in shape_references(body=item.before.body)}
        if any(
            not isinstance(edge.target, PinnedDefinitionReference)
            and edge.target not in allowed
            and edge.target not in inherited
            for edge in shape_references(body=member.definitions[0].body)
        ):
            raise InvalidDecisionError(message="Bind the exact inspected references in the plan")
        return member

    async def _reserve_existing(self, *, item: IncludeCase, parent_id: ReviewCaseId) -> ReviewCase:
        current = await self._reviews.get(scope=self._scope, case_id=item.case_id, version=None)
        if current.version != item.expected_version or current.grouped_by_case_id is not None:
            raise StaleStateError(message="Reload the selected case before grouping it")
        return replace(current, grouped_by_case_id=parent_id, version=current.version + 1)

    async def _current(self, *, inspected: ReviewCase) -> ReviewCase:
        if inspected.scope != self._scope:
            raise InvalidDecisionError(message="Use a coordinated case from this model")
        current = await self._reviews.get(scope=self._scope, case_id=inspected.id, version=None)
        if current != inspected:
            raise StaleStateError(message="Reload the coordinated case before deciding")
        return current

    async def _inspect(
        self,
        *,
        parent: ReviewCase,
        decision: ReviewAction,
    ) -> tuple[ReviewImpact, tuple[MemberEffect, ...]]:
        revision = await self._revisions.revision(scope=self._scope)
        if isinstance(decision, Accept) and revision != parent.guarded_workspace_revision:
            raise StaleStateError(
                message="Reload the workspace and inspect a new coordinated review"
            )
        members = [
            await self._reviews.get(scope=self._scope, case_id=item.case_id, version=None)
            for item in parent.members
        ]
        effects = await self._mapping_effects(
            effects=member_effects(parent=parent, members=members, decision=decision)
        )
        proposed = tuple(
            definition_change(before=effect.before.before_definition, after=definition)
            for effect in effects
            for definition in effect.definitions
        )
        change = parent.dependency_change
        accepted = isinstance(decision, Accept)
        pins = () if self._resolver is None else await self._resolver.selected(scope=self._scope)
        target = change.request.after if accepted and change is not None else pins
        blockers = ()
        if accepted and (proposed or change is not None):
            active = await self._definitions.active(scope=self._scope)
            prospective = {item.id: item for item in active}
            prospective.update((item.id, item) for effect in effects for item in effect.definitions)
            for effect in effects:
                effect.before.require_current_endpoints(
                    active=tuple(prospective.values()), proposed=effect.definitions
                )
            if change is not None:
                dependencies = await inspect_upgrade(
                    scope=self._scope,
                    change=change,
                    resolver=self._resolver,
                )
                archives = change.after_bundles
            else:
                archives = (
                    ()
                    if self._resolver is None
                    else await self._resolver.materialize(
                        scope=self._scope,
                        pins=pins,
                    )
                )
                dependencies = dependency_definitions(scope=self._scope, bundles=archives)
            blockers = check_definition_changes(
                scope=self._scope,
                active=active,
                changes=proposed,
                dependencies=dependencies,
                ontologies=await review_ontology_resources(
                    scope=self._scope,
                    selected=self._packs,
                    dependencies=archives,
                ),
            )
        invalidated = (
            tuple(
                dict.fromkeys(
                    identity
                    for item in proposed
                    for definition in item.before
                    for identity in definition.decision_ids
                )
            )
            if change is not None
            else ()
        )
        related: list[ReviewCaseId] = []
        for effect in effects:
            if (
                effect.source_changes
                and (earlier := effect.before.correction_of_case_id) is not None
            ):
                related.append(earlier)
                confirmations = await affected_confirmations(
                    repository=self._reviews,
                    correction=effect.before,
                )
                related.extend(item.id for item in confirmations)
        return ReviewImpact(
            changes=ChangeSet(
                scope=self._scope,
                comparison=ComparisonKind.PROPOSAL,
                compatibility=Compatibility.COMPATIBLE
                if change is None
                else Compatibility.UNDETERMINED,
                changes=proposed,
                before_dependencies=pins,
                after_dependencies=target,
                source_alignment_changes=tuple(
                    change for effect in effects for change in effect.source_changes
                ),
                reference_disposition_changes=tuple(
                    change for effect in effects for change in effect.reference_changes
                ),
            ),
            workspace_revision=revision,
            affected_case_ids=tuple(
                dict.fromkeys((parent.id, *(item.id for item in members), *related))
            ),
            invalidated_decision_ids=invalidated,
            blockers=blockers,
            dependency_change=change,
        ), effects

    async def preview(self, *, case: ReviewCase, decision: ReviewAction) -> ReviewImpact:
        """Inspect combined effects without mutating the workspace."""
        async with self._transaction.begin():
            impact, _ = await self._inspect(
                parent=await self._current(inspected=case), decision=decision
            )
            return impact

    async def decide(
        self,
        *,
        case: ReviewCase,
        decision: ReviewAction,
        actor: str,
        idempotency_key: str | None,
    ) -> ReviewReceipt:
        """Apply all member effects or release them together."""
        TextValidation.require_text(value=actor, field="Actor")
        if case.scope != self._scope:
            raise InvalidDecisionError(message="Use a coordinated case from this model")
        invocation = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="decide_review",
            actor=actor,
            key=idempotency_key,
            intent=record_value(value=(case, decision)),
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=invocation, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                if claim.resource_kind != "decision":
                    raise InvalidDecisionError(message="The stored review outcome is invalid")
                return await self._reviews.receipt(
                    scope=self._scope,
                    decision_id=DecisionId(value=claim.resource_id),
                )
            receipt = await self._commit(
                parent=await self._current(inspected=case),
                decision=decision,
                actor=actor,
            )
            await self._operations.complete(
                invocation=invocation,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="decision",
                    resource_id=receipt.decision_id.value,
                ),
            )
            return receipt

    async def _commit(
        self,
        *,
        parent: ReviewCase,
        decision: ReviewAction,
        actor: str,
    ) -> ReviewReceipt:
        impact, effects = await self._inspect(parent=parent, decision=decision)
        if impact.blockers:
            raise InvalidDecisionError(
                message="Resolve the combined review's shape blockers",
                issues=impact.blockers,
            )
        change = parent.dependency_change
        if change is not None and isinstance(decision, Accept):
            if self._resolver is None:
                raise MissingCapabilityError(message="Configure writable dependency selections")
            await self._resolver.replace(
                scope=self._scope,
                before=change.request.before,
                after=change.request.after,
            )
        now = datetime.now(tz=UTC)
        identity = DecisionId(value=uuid4().hex)
        revision = impact.workspace_revision + 1
        member_records: list[DecisionRecord] = []
        released: list[ReviewCaseId] = []
        planned = {item.id for effect in effects for item in effect.definitions}
        ordered = sorted(effects, key=lambda effect: not effect.definitions)
        for effect in ordered:
            await self._reviews.save(case=effect.after, expected_version=effect.before.version)
            if effect.action is None:
                released.append(effect.before.id)
            else:
                action = effect.action
                if isinstance(action, MapToDefinition) and action.definition_id in planned:
                    stored = await self._definitions.get(
                        scope=self._scope,
                        definition_id=action.definition_id,
                        revision=action.definition_revision,
                        name=None,
                    )
                    action = MapToDefinition(definition=stored, reason=action.reason)
                member_records.append(
                    await self._record_member(
                        effect=effect,
                        action=action,
                        identity=identity,
                        actor=actor,
                        now=now,
                        revision=revision,
                    )
                )
        positions = {effect.before.id: index for index, effect in enumerate(effects)}
        member_records.sort(key=lambda record: positions[record.case_id])
        await self._revisions.advance(
            scope=self._scope, expected_revision=impact.workspace_revision
        )
        resolved = replace(parent, status=CaseStatus.RESOLVED, version=parent.version + 1)
        await self._reviews.save(case=resolved, expected_version=parent.version)
        receipt = ReviewReceipt(
            scope=self._scope,
            case_id=parent.id,
            case_version=resolved.version,
            decision_id=identity,
            workspace_revision=revision,
            member_decision_ids=tuple(record.id for record in member_records),
        )
        parent_record = DecisionRecord(
            id=identity,
            scope=self._scope,
            case_id=parent.id,
            case_version=parent.version,
            action=decision,
            actor=actor,
            recorded_at=now,
            change_plan=parent.change_plan,
            dependency_change=change,
            member_decision_ids=receipt.member_decision_ids,
            generated_member_case_ids=tuple(parent.generated_member_case_ids),
            released_case_ids=tuple(released),
            applied_changes=replace(
                impact.changes,
                changes=tuple(
                    change for member in member_records for change in member.applied_changes.changes
                ),
                source_alignment_changes=tuple(
                    change
                    for member in member_records
                    for change in member.applied_changes.source_alignment_changes
                ),
                reference_disposition_changes=tuple(
                    change
                    for member in member_records
                    for change in member.applied_changes.reference_disposition_changes
                ),
            ),
        )
        await self._reviews.record(decision=parent_record, receipt=receipt)
        await self._record_group_audit(
            before=parent, after=resolved, record=parent_record, members=member_records
        )
        return receipt

    async def _record_member(  # noqa: PLR0913 - Pin the group decision, actor, time and revision.
        self,
        *,
        effect: MemberEffect,
        action: ReviewAction,
        identity: DecisionId,
        actor: str,
        now: datetime,
        revision: int,
    ) -> DecisionRecord:
        decision_id = DecisionId(value=uuid4().hex)
        changes: list[DefinitionChange] = []
        if not effect.definitions and effect.before.kind is CaseKind.PROPOSAL:
            await self._definitions.release(definition=effect.before.definitions[0])
        for definition in effect.definitions:
            committed = replace(definition, decision_ids=(*definition.decision_ids, decision_id))
            if effect.before.kind is CaseKind.SOURCE_ALIGNMENT:
                await self._definitions.reserve(
                    definition=replace(
                        committed,
                        status=DefinitionStatus.PROPOSED,
                    )
                )
            await self._definitions.append(definition=committed)
            changes.append(
                definition_change(before=effect.before.before_definition, after=committed)
            )
        record = DecisionRecord(
            id=decision_id,
            scope=self._scope,
            case_id=effect.before.id,
            case_version=effect.before.version,
            action=action,
            actor=actor,
            recorded_at=now,
            group_decision_id=identity,
            proposal_ids=tuple(effect.before.proposal_ids),
            supersedes_decision_id=effect.before.correction_of_decision_id
            if effect.source_changes
            else None,
            applied_changes=ChangeSet(
                scope=self._scope,
                comparison=ComparisonKind.PROPOSAL,
                compatibility=Compatibility.COMPATIBLE,
                changes=changes,
                source_alignment_changes=tuple(
                    replace(change, after=replace(change.after, decision_id=decision_id))
                    if change.after is not None
                    else change
                    for change in effect.source_changes
                ),
                reference_disposition_changes=tuple(
                    replace(change, after=replace(change.after, decision_id=decision_id))
                    if change.after is not None
                    else change
                    for change in effect.reference_changes
                ),
            ),
        )
        if effect.source_changes and effect.before.correction_of_case_id is not None:
            confirmations = await affected_confirmations(
                repository=self._reviews, correction=effect.before
            )
            await reopen_affected_confirmations(
                repository=self._reviews,
                correction=effect.before,
                affected=confirmations,
            )
        await self._reviews.record(
            decision=record,
            receipt=ReviewReceipt(
                scope=self._scope,
                case_id=effect.before.id,
                case_version=effect.after.version,
                decision_id=decision_id,
                workspace_revision=revision,
            ),
        )
        return record

    async def _record_group_audit(
        self,
        *,
        before: ReviewCase,
        after: ReviewCase,
        record: DecisionRecord,
        members: Sequence[DecisionRecord],
    ) -> None:
        event = AuditId(value=uuid4().hex)
        await self._audit.append(
            record=AuditRecord(
                id=event,
                project_id=self._scope.project_id,
                model_id=self._scope.model_id,
                action=AuditAction.DECIDE_REVIEW,
                outcome=AuditOutcome.SUCCEEDED,
                actor=record.actor,
                reason=record.action.reason,
                recorded_at=record.recorded_at,
                before=(_resource(identity=before.id, revision=before.version, value=before),),
                after=(
                    _resource(identity=after.id, revision=after.version, value=after),
                    _resource(identity=record.id, revision=None, value=record),
                ),
            )
        )
        for member in members:
            await self._audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=self._scope.project_id,
                    model_id=self._scope.model_id,
                    parent_id=event,
                    action=AuditAction.DECIDE_REVIEW,
                    outcome=AuditOutcome.SUCCEEDED,
                    actor=member.actor,
                    reason=member.action.reason,
                    recorded_at=member.recorded_at,
                    before=(),
                    after=(
                        _resource(identity=member.id, revision=None, value=member),
                        *(
                            _resource(identity=value.id, revision=value.revision, value=value)
                            for change in member.applied_changes.changes
                            for value in change.after
                        ),
                    ),
                )
            )
