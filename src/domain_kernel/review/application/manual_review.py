"""Manual proposal and decision use cases over a short workspace transaction."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel._shared.application.persistence import Invocation, OperationOutcome
from domain_kernel._shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel._shared.domain.changes import (
    ChangeSet,
    ComparisonKind,
    Compatibility,
    ReferenceDispositionChange,
    SourceAlignmentChange,
)
from domain_kernel._shared.domain.definitions import Definition, typed_definition
from domain_kernel._shared.domain.lifecycle import check_definition_changes, definition_change
from domain_kernel._shared.domain.model_values import Terminology
from domain_kernel._shared.domain.naming import resolve_names
from domain_kernel._shared.domain.record_encoding import record_bytes, record_value
from domain_kernel._shared.domain.shape_graph import validate_model_shapes
from domain_kernel.modeling.domain.dependencies import dependency_definitions
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
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
from domain_kernel.review.domain.decisions import (
    Accept,
    AnswerQuestion,
    ConfirmationMethod,
    ConfirmStatement,
    EditDefinition,
    Exclude,
    MapToDefinition,
    Reject,
)
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.review.domain.models import (
    DecisionRecord,
    ReviewCase,
    ReviewImpact,
    ReviewReceipt,
    preview_case,
    resolve_case,
)
from domain_kernel.review.domain.occurrences import (
    effective_occurrences,
    source_effects,
)
from domain_kernel.review.domain.questions import RequirementKind, ReviewRequirement
from domain_kernel.shared.errors import MissingCapabilityError, ScopeMismatchError, StaleStateError
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence
from domain_kernel.sources.application.citations import recorded_citation
from domain_kernel.sources.application.ports import SourceTransaction
from domain_kernel.sources.domain.errors.evidence_unavailable_error import EvidenceUnavailableError
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.statements import StatementOrigin

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from domain_kernel._shared.application.persistence import (
        AuditRepository,
        IdempotencyRepository,
        TransactionManager,
        WorkspaceRevisions,
    )
    from domain_kernel._shared.domain.authoring import LifecycleOperation
    from domain_kernel._shared.domain.definitions import DefinitionBody
    from domain_kernel.modeling.application.dependencies import PublishedDependencies
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.reference_packs.application.selection_ports import SelectedPacks
    from domain_kernel.review.application.ports import DefinitionRepository, ReviewRepository
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.shared.contracts import ModelScope
    from domain_kernel.shared.hashing import JsonValue
    from domain_kernel.sources.domain.models import Evidence, SourceRevision


def _resource(
    *,
    identity: ReviewCaseId | DecisionId | DefinitionId,
    revision: int | None,
    value: object,
) -> AuditResource:
    return AuditResource(
        resource_id=identity,
        revision=revision,
        content_hash=hash_bytes(content=record_bytes(value=value)),
    )


@final
class ManualReview:
    """Coordinate scope checks, domain transitions and the durable review result."""

    def __init__(  # noqa: PLR0913 - Inject the bound capabilities individually.
        self,
        *,
        scope: ModelScope,
        definitions: DefinitionRepository,
        reviews: ReviewRepository,
        audit: AuditRepository,
        operations: IdempotencyRepository,
        revisions: WorkspaceRevisions,
        transaction: TransactionManager,
        packs: SelectedPacks | None = None,
        resolver: PublishedDependencies | None = None,
    ) -> None:
        """Bind only the repositories used during manual review."""
        self._scope = scope
        self._definitions = definitions
        self._reviews = reviews
        self._audit = audit
        self._operations = operations
        self._revisions = revisions
        self._transaction = transaction
        self._packs = packs
        self._resolver = resolver

    async def propose(  # noqa: PLR0913 - Public proposal fields participate in request identity.
        self,
        *,
        actor: str,
        name: str | None,
        display_name: str | None,
        meaning: str,
        body: DefinitionBody,
        aliases: Sequence[str],
        terminology: Terminology | None,
        reason: str,
        idempotency_key: str | None,
        evidence: Sequence[Evidence] = (),
    ) -> ReviewCase:
        """Reserve a proposed definition and record its author without activating it."""
        lookup_name, label = resolve_names(name=name, display_name=display_name)
        draft = Definition(
            id=DefinitionId(value=uuid4().hex),
            scope=self._scope,
            revision=1,
            name=lookup_name,
            display_name=label,
            meaning=meaning,
            body=body,
            aliases=aliases,
            terminology=Terminology() if terminology is None else terminology,
            rationale=reason,
            evidence=evidence,
        )
        case = ReviewCase(
            id=ReviewCaseId(value=uuid4().hex),
            scope=self._scope,
            kind=CaseKind.PROPOSAL,
            status=CaseStatus.PENDING,
            version=1,
            definitions=(draft,),
            reason=reason,
        )
        invocation = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="propose_change",
            actor=actor,
            key=idempotency_key,
            intent=record_value(
                value=(
                    draft.name,
                    draft.display_name,
                    draft.meaning,
                    draft.body,
                    draft.aliases,
                    draft.terminology,
                    case.reason,
                    *((draft.evidence,) if draft.evidence else ()),
                )
            ),
        )
        event = AuditRecord(
            id=AuditId(value=uuid4().hex),
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            action=AuditAction.PROPOSE_CHANGE,
            outcome=AuditOutcome.SUCCEEDED,
            actor=actor,
            recorded_at=datetime.now(tz=UTC),
            reason=reason,
            before=(),
            after=(_resource(identity=case.id, revision=1, value=case),),
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=invocation, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                if claim.resource_kind != "review_case" or claim.resource_version != "1":
                    raise InvalidDecisionError(message="The stored proposal outcome is invalid")
                return await self._reviews.get(
                    scope=self._scope,
                    case_id=ReviewCaseId(value=claim.resource_id),
                    version=1,
                )
            active = await self._definitions.active(scope=self._scope)
            archives = (
                ()
                if self._resolver is None
                else await self._resolver.materialize(
                    scope=self._scope,
                    pins=await self._resolver.selected(scope=self._scope),
                )
            )
            dependencies = dependency_definitions(scope=self._scope, bundles=archives)
            ontologies = await review_ontology_resources(
                scope=self._scope,
                selected=self._packs,
                dependencies=archives,
            )
            issues = validate_model_shapes(
                scope=self._scope,
                definitions=(*active, draft),
                dependencies=dependencies,
                ontologies=ontologies,
            )
            if issues:
                raise InvalidDecisionError(
                    message="Resolve the proposed definition's shape references first",
                    issues=issues,
                )
            await self._definitions.reserve(definition=draft)
            await self._reviews.add(case=case)
            await self._audit.append(record=event)
            await self._operations.complete(
                invocation=invocation,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="review_case",
                    resource_id=case.id.value,
                    resource_version="1",
                ),
            )
        return case

    async def propose_lifecycle(  # noqa: PLR0913 - Capture command identity and version separately.
        self,
        *,
        definition_id: DefinitionId,
        expected_revision: int,
        actor: str,
        idempotency_key: str | None,
        intent: JsonValue,
        operation: Callable[[Definition], LifecycleOperation],
    ) -> ReviewCase:
        """Store a pending lifecycle case against an inspected definition revision."""
        require_exact(value=definition_id, expected=DefinitionId, field="Definition identity")
        require_exact(value=expected_revision, expected=int, field="Expected revision")
        request = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="propose_lifecycle",
            actor=actor,
            key=idempotency_key,
            intent=[definition_id.value, expected_revision, intent],
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=request, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                if claim.resource_kind != "review_case" or claim.resource_version != "1":
                    raise InvalidDecisionError(message="The stored lifecycle outcome is invalid")
                return await self._reviews.get(
                    scope=self._scope,
                    case_id=ReviewCaseId(value=claim.resource_id),
                    version=1,
                )
            before = await self._definitions.get(
                scope=self._scope,
                definition_id=definition_id,
                name=None,
                revision=None,
            )
            if before.revision != expected_revision:
                raise StaleStateError(
                    message="Inspect the current definition before proposing an edit"
                )
            case = lifecycle_case(operation=operation(before))
            await self._reviews.add(case=case)
            await self._audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=self._scope.project_id,
                    model_id=self._scope.model_id,
                    action=AuditAction.PROPOSE_CHANGE,
                    outcome=AuditOutcome.SUCCEEDED,
                    actor=actor,
                    recorded_at=datetime.now(tz=UTC),
                    reason=case.reason,
                    before=(_resource(identity=before.id, revision=before.revision, value=before),),
                    after=(_resource(identity=case.id, revision=case.version, value=case),),
                )
            )
            await self._operations.complete(
                invocation=request,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="review_case",
                    resource_id=case.id.value,
                    resource_version="1",
                ),
            )
            return case

    async def _selected_pack(self) -> ReferencePack:
        pack = None if self._packs is None else await self._packs.get(scope=self._scope)
        if pack is None:
            raise MissingCapabilityError(
                message="Use a workspace with an explicitly selected reference pack"
            )
        return pack

    async def propose_reference_alignment(
        self,
        *,
        actor: str,
        local_definition: Definition,
        reason: str,
        idempotency_key: str | None,
    ) -> ReviewCase:
        """Request explicit review of one current local definition against its selected pack."""
        if local_definition.scope != self._scope:
            raise ScopeMismatchError
        if local_definition.status is not DefinitionStatus.APPROVED:
            raise InvalidDecisionError(message="Review the local definition before aligning it")
        require_text(value=reason, field="Reference review reason")
        local = typed_definition(
            value=local_definition,
            body_type=type(local_definition.body),
            view_type=Definition,
        )
        request = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="propose_reference_alignment",
            actor=actor,
            key=idempotency_key,
            intent=record_value(value=(local, reason)),
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=request, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                if claim.resource_kind != "review_case" or claim.resource_version != "1":
                    raise InvalidDecisionError(
                        message="The stored reference review request is invalid"
                    )
                return await self._reviews.get(
                    scope=self._scope,
                    case_id=ReviewCaseId(value=claim.resource_id),
                    version=1,
                )
            pack = await self._selected_pack()
            await check_inspected(repository=self._definitions, before=local)
            prior = await prior_disposition(repository=self._reviews, local=local, pack=pack.pin)
            case = ReviewCase(
                id=ReviewCaseId(value=uuid4().hex),
                scope=self._scope,
                kind=CaseKind.REFERENCE_ALIGNMENT,
                status=CaseStatus.PENDING,
                version=1,
                definitions=(local,),
                reason=reason,
                reference_pack=pack.pin,
                reference_before=prior,
            )
            await self._reviews.add(case=case)
            await self._audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=self._scope.project_id,
                    model_id=self._scope.model_id,
                    action=AuditAction.PROPOSE_ALIGNMENT,
                    outcome=AuditOutcome.SUCCEEDED,
                    actor=actor,
                    reason=reason,
                    recorded_at=datetime.now(tz=UTC),
                    before=(_resource(identity=local.id, revision=local.revision, value=local),),
                    after=(_resource(identity=case.id, revision=case.version, value=case),),
                )
            )
            await self._operations.complete(
                invocation=request,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="review_case",
                    resource_id=case.id.value,
                    resource_version="1",
                ),
            )
            return case

    async def propose_confirmation(
        self,
        *,
        actor: str,
        subject: ReviewCase,
        reason: str,
        idempotency_key: str | None,
    ) -> ReviewCase:
        """Open independent confirmation review for an inspected subject."""
        self._check_scope(case=subject)
        require_text(value=reason, field="Confirmation reason")
        request = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="propose_confirmation",
            actor=actor,
            key=idempotency_key,
            intent=record_value(value=(subject, reason)),
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=request, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                if claim.resource_kind != "review_case":
                    raise StaleStateError(message="Inspect the stored confirmation request.")
                return await self._reviews.get(
                    scope=self._scope,
                    case_id=ReviewCaseId(value=claim.resource_id),
                    version=1,
                )
            current = await self._current(inspected=subject)
            if current.kind not in (
                CaseKind.PROPOSAL,
                CaseKind.QUESTION,
                CaseKind.SOURCE_ALIGNMENT,
            ):
                raise InvalidDecisionError(
                    message="Select a definition, question or source interpretation."
                )
            evidence = tuple(
                dict.fromkeys(
                    (
                        *current.evidence,
                        *(proof for item in current.definitions for proof in item.evidence),
                    )
                )
            )
            case = ReviewCase(
                id=ReviewCaseId(value=uuid4().hex),
                scope=self._scope,
                kind=CaseKind.CONFIRMATION,
                status=CaseStatus.PENDING,
                version=1,
                definitions=current.definitions,
                reason=reason,
                confirmation_subject_id=current.id,
                proposal_ids=current.proposal_ids,
                evidence=evidence,
                run_id=current.run_id,
                reconciliation_id=current.reconciliation_id,
                requirements=(
                    ReviewRequirement(
                        kind=RequirementKind.EVIDENCE, code="confirmation_required", required=True
                    ),
                ),
            )
            revision = await self._revisions.revision(scope=self._scope)
            await self._revisions.advance(scope=self._scope, expected_revision=revision)
            await self._reviews.add(case=case)
            await self._audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=self._scope.project_id,
                    model_id=self._scope.model_id,
                    action=AuditAction.PROPOSE_CHANGE,
                    outcome=AuditOutcome.SUCCEEDED,
                    actor=actor,
                    recorded_at=datetime.now(tz=UTC),
                    reason=reason,
                    before=(
                        _resource(identity=current.id, revision=current.version, value=current),
                    ),
                    after=(_resource(identity=case.id, revision=case.version, value=case),),
                )
            )
            await self._operations.complete(
                invocation=request,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="review_case", resource_id=case.id.value, resource_version="1"
                ),
            )
            return case

    async def _check_confirmation(self, *, case: ReviewCase, decision: ReviewAction) -> None:
        if (
            not isinstance(decision, (ConfirmStatement, AnswerQuestion))
            or decision.confirmation is None
        ):
            return
        confirmation = decision.confirmation
        if not isinstance(self._transaction, SourceTransaction):
            raise MissingCapabilityError(
                message="Configure exact confirmation evidence persistence."
            )
        subject_sources: set[SourceRevision] = (
            {item.source for item in case.evidence} if case.kind is CaseKind.CONFIRMATION else set()
        )
        for item in confirmation.evidence:
            if item.source in subject_sources:
                raise InvalidDecisionError(
                    message="Select separately captured confirmation evidence."
                )
            try:
                recorded = await recorded_citation(
                    repository=self._transaction.sources,
                    project_id=self._scope.project_id,
                    expected=item,
                )
            except (EvidenceUnavailableError, SourceRevisionMismatchError, ScopeMismatchError):
                raise InvalidDecisionError(
                    message="Select exact stored confirmation evidence from this project."
                ) from None
            origin = recorded.source.origin
            if confirmation.method is ConfirmationMethod.RECORDED and (
                not isinstance(origin, StatementOrigin)
                or origin.speaker != confirmation.confirmed_by
                or origin.stated_at != confirmation.confirmed_at
                or origin.recorded_by != confirmation.recorded_by
                or origin.recorded_at != confirmation.recorded_at
            ):
                raise InvalidDecisionError(
                    message="Use the recorded statement's exact attribution and timestamps."
                )

    async def reopen_source_case(  # noqa: PLR0913 - Exact selection and retry intent are explicit.
        self,
        *,
        actor: str,
        case_id: ReviewCaseId,
        expected_version: int,
        proposal_ids: Sequence[ProposalId] | None,
        reason: str,
        idempotency_key: str | None,
    ) -> ReviewCase:
        """Open a new review case scoped to still-effective selected occurrences."""
        require_exact(value=case_id, expected=ReviewCaseId, field="Review case ID")
        require_exact(value=expected_version, expected=int, field="Review case version")
        require_text(value=reason, field="Correction reason")
        selected = (
            None
            if proposal_ids is None
            else snapshot_sequence(
                items=proposal_ids,
                item_type=ProposalId,
                field="Selected occurrences",
            )
        )
        request = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="reopen_review_case",
            actor=actor,
            key=idempotency_key,
            intent=record_value(value=(case_id, expected_version, selected, reason)),
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=request, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                if claim.resource_kind != "review_case":
                    raise StaleStateError(message="Inspect the stored correction outcome.")
                return await self._reviews.get(
                    scope=self._scope,
                    case_id=ReviewCaseId(value=claim.resource_id),
                    version=1,
                )
            original = await self._reviews.get(scope=self._scope, case_id=case_id, version=None)
            if original.version != expected_version:
                raise StaleStateError(message="Reload the exact source review before reopening it.")
            case = await capture_correction(
                repository=self._reviews, original=original, selected=selected, reason=reason
            )
            revision = await self._revisions.revision(scope=self._scope)
            await self._revisions.advance(scope=self._scope, expected_revision=revision)
            await self._reviews.add(case=case)
            await self._audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=self._scope.project_id,
                    model_id=self._scope.model_id,
                    action=AuditAction.REOPEN_REVIEW_CASE,
                    outcome=AuditOutcome.SUCCEEDED,
                    actor=actor,
                    recorded_at=datetime.now(tz=UTC),
                    reason=reason,
                    before=(
                        _resource(identity=original.id, revision=original.version, value=original),
                    ),
                    after=(_resource(identity=case.id, revision=case.version, value=case),),
                )
            )
            await self._operations.complete(
                invocation=request,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="review_case", resource_id=case.id.value, resource_version="1"
                ),
            )
            return case

    async def _source_changes(
        self,
        *,
        case: ReviewCase,
        decision: ReviewAction,
    ) -> tuple[SourceAlignmentChange, ...]:
        if case.kind is not CaseKind.SOURCE_ALIGNMENT or not isinstance(
            decision, (MapToDefinition, Exclude, Accept, EditDefinition)
        ):
            return ()
        if isinstance(decision, MapToDefinition):
            target = decision.definition
            if target.scope != self._scope:
                raise ScopeMismatchError
            if target.status is not DefinitionStatus.APPROVED:
                raise InvalidDecisionError(message="Inspect the approved local meaning.")
            await check_inspected(repository=self._definitions, before=target)
            if target.body.kind is not case.definitions[0].body.kind:
                raise InvalidDecisionError(message="Map meanings with the same definition kind.")
        await check_source_citations(transaction=self._transaction, case=case)
        decisions = await source_decisions(repository=self._reviews, scope=self._scope)
        return source_effects(
            case=case, decision=decision, effective=effective_occurrences(decisions=decisions)
        )

    async def _reference_changes(
        self,
        *,
        case: ReviewCase,
        decision: ReviewAction,
    ) -> tuple[ReferenceDispositionChange, ...]:
        if case.kind is not CaseKind.REFERENCE_ALIGNMENT or isinstance(decision, Reject):
            return ()
        local = case.definitions[0]
        pack = await self._selected_pack()
        await check_inspected(repository=self._definitions, before=local)
        previous = await prior_disposition(repository=self._reviews, local=local, pack=pack.pin)
        return inspect_alignment(case=case, decision=decision, pack=pack, previous=previous)

    def _check_scope(self, *, case: ReviewCase) -> None:
        require_exact(value=case, expected=ReviewCase, field="Inspected review case")
        if case.scope != self._scope:
            raise InvalidDecisionError(message="Use a review case from this model workspace")

    async def _current(self, *, inspected: ReviewCase) -> ReviewCase:
        current = await self._reviews.get(scope=self._scope, case_id=inspected.id, version=None)
        if current != inspected:
            raise StaleStateError(message="Reload and inspect the current review case")
        return current

    async def _impact(self, *, case: ReviewCase, decision: ReviewAction) -> ReviewImpact:
        amendments = preview_case(case=case, decision=decision)
        await self._check_confirmation(case=case, decision=decision)
        changes = tuple(
            definition_change(before=case.before_definition, after=item) for item in amendments
        )
        issues = ()
        if changes:
            if case.before_definition is not None:
                await check_inspected(repository=self._definitions, before=case.before_definition)
            active = await self._definitions.active(scope=self._scope)
            archives = (
                ()
                if self._resolver is None
                else await self._resolver.materialize(
                    scope=self._scope,
                    pins=await self._resolver.selected(scope=self._scope),
                )
            )
            dependencies = dependency_definitions(scope=self._scope, bundles=archives)
            ontologies = await review_ontology_resources(
                scope=self._scope,
                selected=self._packs,
                dependencies=archives,
            )
            issues = check_definition_changes(
                scope=self._scope,
                active=active,
                changes=changes,
                dependencies=dependencies,
                ontologies=ontologies,
            )
        reference_changes = await self._reference_changes(case=case, decision=decision)
        occurrence_changes = await self._source_changes(case=case, decision=decision)
        impacted = (case.id,)
        if occurrence_changes and case.correction_of_case_id is not None:
            confirmations = await affected_confirmations(repository=self._reviews, correction=case)
            impacted = (case.id, case.correction_of_case_id, *(item.id for item in confirmations))
        return ReviewImpact(
            changes=ChangeSet(
                scope=self._scope,
                comparison=ComparisonKind.PROPOSAL,
                compatibility=Compatibility.COMPATIBLE,
                changes=changes,
                reference_disposition_changes=reference_changes,
                source_alignment_changes=occurrence_changes,
            ),
            workspace_revision=await self._revisions.revision(scope=self._scope),
            affected_case_ids=impacted,
            blockers=issues,
        )

    async def preview(self, *, case: ReviewCase, decision: ReviewAction) -> ReviewImpact:
        """Recheck the inspected case and calculate effects without writes."""
        self._check_scope(case=case)
        async with self._transaction.begin():
            current = await self._current(inspected=case)
            return await self._impact(case=current, decision=decision)

    async def decide(
        self,
        *,
        case: ReviewCase,
        decision: ReviewAction,
        actor: str,
        idempotency_key: str | None,
    ) -> ReviewReceipt:
        """Commit inspected effects, decision, audit and replay receipt atomically."""
        self._check_scope(case=case)
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
                    raise InvalidDecisionError(message="The stored decision outcome is invalid")
                return await self._reviews.receipt(
                    scope=self._scope,
                    decision_id=DecisionId(value=claim.resource_id),
                )
            current = await self._current(inspected=case)
            receipt = await self._commit(case=current, decision=decision, actor=actor)
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
        case: ReviewCase,
        decision: ReviewAction,
        actor: str,
    ) -> ReviewReceipt:
        impact = await self._impact(case=case, decision=decision)
        if impact.blockers:
            raise InvalidDecisionError(message="Inspect and resolve the preview's shape blockers")
        if isinstance(decision, (ConfirmStatement, AnswerQuestion)) and (
            decision.confirmation is not None
            and decision.confirmation.method is ConfirmationMethod.AUTHENTICATED
            and decision.confirmation.authenticated_actor != actor
        ):
            raise InvalidDecisionError(
                message="Submit an authenticated confirmation as its verified actor."
            )
        recorded_at = datetime.now(tz=UTC)
        identity = DecisionId(value=uuid4().hex)
        resolved = resolve_case(
            case=case,
            decision=decision,
            actor=actor,
            expected_version=case.version,
            now=recorded_at,
            decision_id=identity,
        )
        amended = tuple(
            replace(
                change,
                after=tuple(
                    replace(value, decision_ids=(*value.decision_ids, identity))
                    for value in change.after
                ),
            )
            for change in impact.definition_changes
        )
        revision = impact.workspace_revision
        if isinstance(decision, Reject):
            if case.kind is CaseKind.PROPOSAL:
                await self._definitions.release(definition=case.definitions[0])
        else:
            for change in amended:
                for definition in change.after:
                    if case.kind is CaseKind.SOURCE_ALIGNMENT:
                        await self._definitions.reserve(
                            definition=replace(
                                definition,
                                status=DefinitionStatus.PROPOSED,
                            )
                        )
                    await self._definitions.append(definition=definition)
            await self._revisions.advance(scope=self._scope, expected_revision=revision)
            revision += 1
        await self._reviews.save(case=resolved, expected_version=case.version)
        if impact.source_alignment_changes and case.correction_of_case_id is not None:
            confirmations = await affected_confirmations(repository=self._reviews, correction=case)
            await reopen_affected_confirmations(
                repository=self._reviews,
                correction=case,
                affected=confirmations,
            )
        receipt = ReviewReceipt(
            scope=self._scope,
            case_id=case.id,
            case_version=resolved.version,
            decision_id=identity,
            workspace_revision=revision,
        )
        record = DecisionRecord(
            id=identity,
            scope=self._scope,
            case_id=case.id,
            case_version=case.version,
            action=decision,
            actor=actor,
            recorded_at=recorded_at,
            proposal_ids=tuple(case.proposal_ids),
            supersedes_decision_id=(
                case.correction_of_decision_id if impact.source_alignment_changes else None
            ),
            applied_changes=replace(
                impact.changes,
                changes=amended,
                source_alignment_changes=tuple(
                    replace(change, after=replace(change.after, decision_id=identity))
                    if change.after is not None
                    else change
                    for change in impact.source_alignment_changes
                ),
                reference_disposition_changes=tuple(
                    replace(change, after=replace(change.after, decision_id=identity))
                    if change.after is not None
                    else change
                    for change in impact.changes.reference_disposition_changes
                ),
            ),
        )
        await self._reviews.record(decision=record, receipt=receipt)
        await self._audit.append(
            record=AuditRecord(
                id=AuditId(value=uuid4().hex),
                project_id=self._scope.project_id,
                model_id=self._scope.model_id,
                action=AuditAction.DECIDE_REVIEW,
                outcome=AuditOutcome.SUCCEEDED,
                actor=actor,
                recorded_at=recorded_at,
                reason=decision.reason,
                before=(_resource(identity=case.id, revision=case.version, value=case),),
                after=(
                    _resource(identity=case.id, revision=resolved.version, value=resolved),
                    _resource(identity=identity, revision=None, value=record),
                    *(
                        _resource(identity=value.id, revision=value.revision, value=value)
                        for change in amended
                        for value in change.after
                    ),
                ),
            )
        )
        return receipt
