"""Coordinate checkpointed discovery without retaining transactions through inference."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, final
from uuid import uuid4

from domain_kernel._shared.application.persistence import (
    Invocation,
    OperationOutcome,
    keep_work_leased,
)
from domain_kernel._shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.discovery.application.ports import ExtractionTransaction
from domain_kernel.discovery.application.prompts import capture_prompt
from domain_kernel.discovery.application.run_ports import DiscoveryTransaction
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.models import (
    DiscoveryFailure,
    DiscoveryProgress,
    DiscoveryResult,
    DiscoveryRun,
    RunStatus,
    SourceCheckpoint,
)
from domain_kernel.discovery.domain.schema_options import SchemaDiscoveryOptions
from domain_kernel.discovery.domain.schema_policy import SCHEMA_V23
from domain_kernel.review.application.ports import ReviewTransaction
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import (
    DomainKernelError,
    IdempotencyConflictError,
    InferenceError,
    MissingCapabilityError,
    ScopeMismatchError,
    StaleStateError,
)
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validation import require_exact, snapshot_sequence
from domain_kernel.sources.domain.models import SourceRevision

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine, Sequence

    from domain_kernel._shared.application.catalogs import CatalogTransaction
    from domain_kernel._shared.application.persistence import Lease, UnitOfWorkFactory
    from domain_kernel.discovery.application.extraction import Extraction
    from domain_kernel.discovery.domain.bindings import HeldRelationship, RelationshipBinding
    from domain_kernel.discovery.domain.coverage import DiscoveryCoverage
    from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
    from domain_kernel.discovery.domain.models import (
        DiscoveryDraft,
        InterpretationContext,
        ProgressCallback,
    )
    from domain_kernel.reconciliation.domain.models import Alignment
    from domain_kernel.shared.contracts import ModelScope, Page
    from domain_kernel.shared.hashing import JsonValue
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


_IN_FLIGHT = frozenset({RunStatus.INGESTING, RunStatus.EXTRACTING, RunStatus.RECONCILING})
_RECOVERABLE = frozenset({RunStatus.PARTIALLY_FAILED, RunStatus.FAILED, RunStatus.CANCELLED})
_HEARTBEAT_SECONDS = 20


class AlignmentOperation(Protocol):
    """Prepare the ordinary, independently callable reconciliation stage."""

    async def __call__(
        self,
        *,
        actor: str,
        discovery_id: DiscoveryDraftId,
        idempotency_key: str,
    ) -> Alignment:
        """Return the durable preparation for this exact draft."""
        ...


@dataclass(kw_only=True)
class _Worker:
    invocation: Invocation
    lease: Lease
    run: DiscoveryRun
    progress: ProgressCallback | None


def _v23_requested_intent(*, intent: tuple[JsonValue, ...], coverage: str) -> JsonValue:
    """Reconstruct only the old v23 wire identity, never its retired selectors."""
    revisions, instructions, override, options = intent
    if not isinstance(options, dict) or not isinstance(fields := options.get("fields"), dict):
        raise TypeError("Encode the captured discovery options as a record.")
    return (
        revisions,
        instructions,
        override,
        {
            **options,
            "fields": {
                **fields,
                "workflow_version": "v23",
                "coverage_strategy": coverage,
                "reference_guidance": "late_mapping",
            },
        },
    )


@final
class DiscoveryWorkflow:
    """Run independently recoverable source tasks under one immutable run identity."""

    def __init__(
        self,
        *,
        scope: ModelScope,
        resources: UnitOfWorkFactory[CatalogTransaction],
        extraction: Extraction | None,
        align: AlignmentOperation,
    ) -> None:
        """Bind the original client's capabilities and workspace scope."""
        self._scope = scope
        self._resources = resources
        self._extraction = extraction
        self._align = align

    @asynccontextmanager
    async def _transaction(self) -> AsyncGenerator[DiscoveryTransaction]:
        async with self._resources() as transaction:
            if not isinstance(transaction, DiscoveryTransaction):
                raise MissingCapabilityError(message="Configure durable discovery run persistence.")
            async with transaction.begin():
                yield transaction

    async def get(self, *, run_id: DiscoveryRunId) -> DiscoveryResult:
        """Return a run independently of any inference configuration."""
        require_exact(value=run_id, expected=DiscoveryRunId, field="Discovery run ID")
        async with self._transaction() as transaction:
            return (await transaction.discovery_runs.get(scope=self._scope, run_id=run_id)).snapshot

    async def bindings(
        self, *, run_id: DiscoveryRunId, source: SourceRevision
    ) -> tuple[RelationshipBinding, ...]:
        """Read resolved and held relationships from one exact source in a run."""
        draft = await self._source_draft(run_id=run_id, source=source)
        return tuple(draft.relationship_bindings) if draft is not None else ()

    async def held_relationships(
        self, *, run_id: DiscoveryRunId, source: SourceRevision
    ) -> tuple[HeldRelationship, ...]:
        """Read verified claims awaiting endpoint review."""
        draft = await self._source_draft(run_id=run_id, source=source)
        return tuple(draft.held_relationships) if draft is not None else ()

    async def coverage(
        self, *, run_id: DiscoveryRunId, source: SourceRevision
    ) -> DiscoveryCoverage | None:
        """Read persisted omission coverage for a captured source."""
        draft = await self._source_draft(run_id=run_id, source=source)
        return (
            next((entry for entry in draft.coverage if entry.source == source), None)
            if draft
            else None
        )

    async def _source_draft(
        self, *, run_id: DiscoveryRunId, source: SourceRevision
    ) -> DiscoveryDraft | None:
        require_exact(value=run_id, expected=DiscoveryRunId, field="Discovery run ID")
        require_exact(value=source, expected=SourceRevision, field="Source revision")
        if source.project_id != self._scope.project_id:
            raise ScopeMismatchError
        async with self._transaction() as transaction:
            run = await transaction.discovery_runs.get(scope=self._scope, run_id=run_id)
            task = next((task for task in run.tasks if task.source == source), None)
            if task is None:
                raise ValueError("Select a source revision captured by this run.")
            if task.draft_id is None:
                return None
            if not isinstance(transaction, ExtractionTransaction):
                raise MissingCapabilityError(message="Configure durable extraction persistence.")
            return await transaction.extraction.draft(identifier=task.draft_id, scope=self._scope)

    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[DiscoveryResult]:
        """Page through this workspace's persisted runs."""
        async with self._transaction() as transaction:
            return await transaction.discovery_runs.list(
                scope=self._scope, limit=limit, cursor=cursor
            )

    async def discover(  # noqa: PLR0913 - The workflow pins the request and checkpoint explicitly.
        self,
        *,
        actor: str,
        context: InterpretationContext,
        sources: Sequence[SourceRevision],
        additional_instructions: str | None,
        prompt_override: str | None,
        idempotency_key: str | None,
        on_progress: ProgressCallback | None,
        schema_options: SchemaDiscoveryOptions | None = None,
    ) -> DiscoveryResult:
        """Register discovery intent before performing any inference or review preparation."""
        if self._extraction is None:
            raise MissingCapabilityError(
                message="Configure a model gateway to discover source meanings."
            )
        from domain_kernel.discovery.application.structured_output import (  # noqa: PLC0415 - Avoid the workflow and extraction import cycle.
            response_schema,
        )

        revisions = snapshot_sequence(
            items=sources, item_type=SourceRevision, field="Source revisions"
        )
        if not revisions or len(set(revisions)) != len(revisions):
            raise ValueError("Select distinct exact ingested source revisions.")
        if any(item.project_id != self._scope.project_id for item in revisions):
            raise ScopeMismatchError
        schema_options = SchemaDiscoveryOptions() if schema_options is None else schema_options
        require_exact(value=schema_options, expected=SchemaDiscoveryOptions, field="Schema options")
        if any(item.revision not in revisions for item in schema_options.source_context):
            raise ValueError("Supply source context only for selected revisions.")
        self._extraction.require_discovery()
        schema = response_schema()
        prompt = capture_prompt(
            additional_instructions=additional_instructions,
            prompt_override=prompt_override,
            schema_json=schema,
            schema_options=schema_options,
        )
        intent = (
            record_value(value=revisions),
            additional_instructions,
            prompt_override,
            record_value(value=schema_options),
        )
        request = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="discover",
            actor=actor,
            key=idempotency_key,
            intent=intent,
        )
        run = await self._register(
            request=request,
            intent=intent,
            new=DiscoveryRun(
                snapshot=DiscoveryResult(
                    id=DiscoveryRunId(value=uuid4().hex),
                    scope=self._scope,
                    version=1,
                    status=RunStatus.INGESTING,
                    failures=(),
                    discovery_id=None,
                    reconciliation_id=None,
                    context=context,
                    prompt=prompt,
                ),
                actor=actor,
                schema_json=schema,
                tasks=tuple(SourceCheckpoint(source=item) for item in revisions),
                workflow_profile=self._extraction.workflow_profile,
                schema_version=SCHEMA_V23,
            ),
        )
        if run.snapshot.status in _IN_FLIGHT:
            return await self._advance(run=run, on_progress=on_progress)
        return run.snapshot

    async def _register(
        self, *, request: Invocation, intent: tuple[JsonValue, ...], new: DiscoveryRun
    ) -> DiscoveryRun:
        async with self._transaction() as transaction:
            owner = uuid4().hex
            try:
                claim = await transaction.operations.claim(invocation=request, owner=owner)
            except IdempotencyConflictError:
                for coverage in ("parent_only", "focused"):
                    original = Invocation.resolve(
                        project_id=request.project_id,
                        model_id=request.model_id,
                        operation=request.operation,
                        actor=request.actor,
                        key=request.idempotency_key,
                        intent=_v23_requested_intent(intent=intent, coverage=coverage),
                    )
                    try:
                        replay = await transaction.operations.claim(
                            invocation=original, owner=owner
                        )
                    except IdempotencyConflictError:
                        continue
                    if isinstance(replay, OperationOutcome):
                        restored = await self._restore_outcome(
                            transaction=transaction, outcome=replay
                        )
                        if restored.schema_version == SCHEMA_V23:
                            return restored
                    break
                raise
            if isinstance(claim, OperationOutcome):
                return await self._restore_outcome(transaction=transaction, outcome=claim)
            await transaction.discovery_runs.add(run=new)
            await self._audit(
                transaction=transaction, run=new, actor=new.actor, action=AuditAction.DISCOVER
            )
            await transaction.operations.complete(
                invocation=request,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="discovery_run", resource_id=new.snapshot.id.value
                ),
            )
            return new

    async def continue_discovery(
        self,
        *,
        actor: str,
        run_id: DiscoveryRunId,
        context: InterpretationContext,
        idempotency_key: str | None,
    ) -> DiscoveryResult:
        """Open a linked run over the persisted deferred spans of a completed draft."""
        require_exact(value=run_id, expected=DiscoveryRunId, field="Parent discovery run ID")
        parent, tasks = await self._continuation_source(run_id=run_id)
        request = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="continue_discovery",
            actor=actor,
            key=idempotency_key,
            intent=run_id.value,
        )
        captured = replace(
            parent.snapshot.context,
            approved_definitions=context.approved_definitions,
            workspace_revision=context.workspace_revision,
        )
        new = DiscoveryRun(
            snapshot=DiscoveryResult(
                id=DiscoveryRunId(value=uuid4().hex),
                scope=self._scope,
                version=1,
                status=RunStatus.INGESTING,
                failures=(),
                discovery_id=None,
                reconciliation_id=None,
                context=captured,
                prompt=parent.snapshot.prompt,
                parent_run_id=run_id,
            ),
            actor=actor,
            schema_json=parent.schema_json,
            tasks=tasks,
            workflow_profile=parent.workflow_profile,
            schema_version=parent.schema_version,
        )
        run = await self._register_continuation(request=request, parent=parent, new=new)
        return (
            await self._advance(run=run, on_progress=None)
            if run.snapshot.status in _IN_FLIGHT
            else run.snapshot
        )

    async def _continuation_source(
        self, *, run_id: DiscoveryRunId
    ) -> tuple[DiscoveryRun, tuple[SourceCheckpoint, ...]]:
        if self._extraction is None:
            raise MissingCapabilityError(
                message="Configure the original discovery gateway to continue omissions."
            )
        async with self._transaction() as transaction:
            parent = await transaction.discovery_runs.get(scope=self._scope, run_id=run_id)
            if parent.workflow_profile != self._extraction.workflow_profile:
                raise StaleStateError(
                    message="Continue with the original discovery workflow and provider profile."
                )
            if not isinstance(transaction, ExtractionTransaction):
                raise MissingCapabilityError(message="Configure durable extraction persistence.")
            selected: list[SourceCheckpoint] = []
            pending = False
            if parent.schema_version != SCHEMA_V23:
                raise StaleStateError(message="Start a new discovery run with the current SDK.")
            for task in parent.tasks:
                if task.draft_id is None:
                    selected.append(SourceCheckpoint(source=task.source))
                    continue
                draft = await transaction.extraction.draft(
                    identifier=task.draft_id, scope=self._scope
                )
                if any(manifest.has_deferred for manifest in draft.coverage):
                    selected.append(SourceCheckpoint(source=task.source))
                    pending = True
                else:
                    selected.append(task)
        if not pending:
            raise StaleStateError(
                message="Select a reviewable discovery draft with deferred omission work."
            )
        return parent, tuple(selected)

    async def _register_continuation(
        self, *, request: Invocation, parent: DiscoveryRun, new: DiscoveryRun
    ) -> DiscoveryRun:
        # Coalesce all callers for one immutable parent version while preserving caller attribution.
        chain = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="link_discovery_continuation",
            actor=parent.actor,
            key=parent.snapshot.id.value,
            intent=parent.snapshot.id.value,
        )
        async with self._transaction() as transaction:
            claim = await transaction.operations.claim(invocation=request, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                return await self._restore_outcome(transaction=transaction, outcome=claim)
            linkage = await transaction.operations.claim(invocation=chain, owner=uuid4().hex)
            if isinstance(linkage, OperationOutcome):
                run = await self._restore_outcome(transaction=transaction, outcome=linkage)
            else:
                run = new
                await transaction.discovery_runs.add(run=run)
                await self._audit(
                    transaction=transaction,
                    run=run,
                    actor=request.actor,
                    action=AuditAction.RESUME_DISCOVERY,
                )
                await transaction.operations.complete(
                    invocation=chain,
                    lease=linkage,
                    outcome=OperationOutcome(
                        resource_kind="discovery_run", resource_id=run.snapshot.id.value
                    ),
                )
            await transaction.operations.complete(
                invocation=request,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="discovery_run", resource_id=run.snapshot.id.value
                ),
            )
            return run

    async def resume(
        self,
        *,
        actor: str,
        run_id: DiscoveryRunId,
        idempotency_key: str | None,
        on_progress: ProgressCallback | None,
    ) -> DiscoveryResult:
        """Recover the stored request, using its original prompt and source checkpoints."""
        require_exact(value=run_id, expected=DiscoveryRunId, field="Discovery run ID")
        request = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="resume_discovery",
            actor=actor,
            key=idempotency_key,
            intent=run_id.value,
        )
        async with self._transaction() as transaction:
            claim = await transaction.operations.claim(invocation=request, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                current = await self._restore_outcome(transaction=transaction, outcome=claim)
            else:
                current = await transaction.discovery_runs.get(scope=self._scope, run_id=run_id)
                if current.snapshot.status not in _RECOVERABLE | _IN_FLIGHT:
                    raise StaleStateError(message="Resume a run with unfinished discovery work.")
                if self._extraction is None:
                    raise MissingCapabilityError(
                        message="Configure a model gateway to resume discovery."
                    )
                await self._audit(
                    transaction=transaction,
                    run=current,
                    actor=actor,
                    action=AuditAction.RESUME_DISCOVERY,
                )
                await transaction.operations.complete(
                    invocation=request,
                    lease=claim,
                    outcome=OperationOutcome(
                        resource_kind="discovery_run",
                        resource_id=run_id.value,
                        resource_version=str(current.snapshot.version),
                    ),
                )
        if isinstance(claim, OperationOutcome) and (
            current.snapshot.status not in _IN_FLIGHT
            and claim.resource_version != str(current.snapshot.version)
        ):
            return current.snapshot
        return await self._advance(run=current, on_progress=on_progress)

    async def _restore_outcome(
        self,
        *,
        transaction: DiscoveryTransaction,
        outcome: OperationOutcome,
    ) -> DiscoveryRun:
        if outcome.resource_kind != "discovery_run":
            raise StaleStateError(message="Inspect the stored discovery request.")
        return await transaction.discovery_runs.get(
            scope=self._scope, run_id=DiscoveryRunId(value=outcome.resource_id)
        )

    async def _audit(
        self,
        *,
        transaction: DiscoveryTransaction,
        run: DiscoveryRun,
        actor: str,
        action: AuditAction,
    ) -> None:
        await transaction.audit.append(
            record=AuditRecord(
                id=AuditId(value=uuid4().hex),
                project_id=self._scope.project_id,
                model_id=self._scope.model_id,
                action=action,
                outcome=AuditOutcome.STARTED,
                actor=actor,
                recorded_at=datetime.now(tz=UTC),
                reason="Capture the exact discovery run and its prompt.",
                before=(),
                after=(
                    AuditResource(
                        resource_id=run.snapshot.id,
                        revision=run.snapshot.version,
                        content_hash=hash_json(value=record_value(value=run)),
                    ),
                ),
            )
        )

    async def _advance(
        self, *, run: DiscoveryRun, on_progress: ProgressCallback | None
    ) -> DiscoveryResult:
        if self._extraction is None:
            raise MissingCapabilityError(message="Configure a model gateway to resume discovery.")
        identity = run.snapshot.id
        invocation = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="advance_discovery",
            actor=run.actor,
            key=identity.value,
            intent=identity.value,
        )
        async with self._transaction() as transaction:
            lease = await transaction.operations.claim(invocation=invocation, owner=uuid4().hex)
            if isinstance(lease, OperationOutcome):
                return (
                    await self._restore_outcome(transaction=transaction, outcome=lease)
                ).snapshot
            current = await transaction.discovery_runs.get(scope=self._scope, run_id=identity)
            if current.schema_version != SCHEMA_V23:
                await transaction.operations.release(invocation=invocation, lease=lease)
                raise StaleStateError(message="Start a new discovery run with the current SDK.")
            if current.snapshot.status in (RunStatus.NEEDS_REVIEW, RunStatus.READY_TO_PREPARE):
                await transaction.operations.release(invocation=invocation, lease=lease)
                return current.snapshot
        worker = _Worker(invocation=invocation, lease=lease, run=current, progress=on_progress)
        try:
            for task in current.tasks:
                if task.draft_id is None:
                    await self._run_task(worker=worker, task=task, extraction=self._extraction)
            try:
                await self._consolidate(worker=worker, extraction=self._extraction)
            except DomainKernelError as error:
                await self._checkpoint(
                    worker=worker,
                    status=(
                        RunStatus.PARTIALLY_FAILED
                        if worker.run.snapshot.reconciliation_id
                        else RunStatus.FAILED
                    ),
                    modeling_error=error,
                )
                return worker.run.snapshot
            if worker.run.snapshot.status is RunStatus.PARTIALLY_FAILED:
                return worker.run.snapshot
            await self._finish(worker=worker)
        except asyncio.CancelledError:
            with suppress(StaleStateError):
                await self._checkpoint(worker=worker, status=RunStatus.CANCELLED, report=False)
            raise
        finally:
            with suppress(StaleStateError):
                async with self._transaction() as transaction:
                    await transaction.operations.release(invocation=invocation, lease=worker.lease)
        return worker.run.snapshot

    async def _run_task(
        self,
        *,
        worker: _Worker,
        task: SourceCheckpoint,
        extraction: Extraction,
    ) -> None:
        from domain_kernel.discovery.application.extraction import (  # noqa: PLC0415 - Avoid the workflow and extraction import cycle.
            ExtractionRequest,
        )

        run = worker.run
        snapshot = run.snapshot
        key = hash_json(value=record_value(value=(snapshot.id, task.source))).value
        draft_id = task.draft_id
        if draft_id is None:
            await self._checkpoint(worker=worker, status=RunStatus.EXTRACTING)
            try:
                if run.workflow_profile != extraction.workflow_profile:
                    raise StaleStateError(
                        message="Resume with the original discovery workflow and provider profile."
                    )
                draft = await self._wait(
                    worker=worker,
                    work=extraction.extract_captured(
                        actor=run.actor,
                        idempotency_key=key,
                        request=ExtractionRequest(
                            context=snapshot.context,
                            revisions=(task.source,),
                            prompt=snapshot.prompt,
                            schema=run.schema_json,
                            callback=None,
                            run_id=snapshot.id,
                            ancestry=await self._ancestry(
                                parent=snapshot.parent_run_id, source=task.source
                            ),
                            schema_version=run.schema_version,
                        ),
                    ),
                )
            except DomainKernelError as error:
                await self._fail_task(worker=worker, task=task, error=error)
                return
            draft_id = draft.id
            task = replace(task, draft_id=draft_id, failure=None)
        await self._checkpoint(worker=worker, status=RunStatus.RECONCILING, task=task)

    async def _consolidate(self, *, worker: _Worker, extraction: Extraction) -> None:
        from domain_kernel.discovery.application.extraction import ExtractionRequest  # noqa: PLC0415 - Avoid the workflow and extraction import cycle.

        run = worker.run
        snapshot = run.snapshot
        identities = tuple(task.draft_id for task in run.tasks if task.draft_id is not None)
        if not identities:
            return
        if run.workflow_profile != extraction.workflow_profile:
            raise StaleStateError(message="Resume with the captured schema discovery profile.")
        prior = None
        async with self._transaction() as transaction:
            if not isinstance(transaction, ExtractionTransaction):
                raise MissingCapabilityError(message="Reopen the captured source observations.")
            drafts = tuple(
                [
                    await transaction.extraction.draft(identifier=identity, scope=self._scope)
                    for identity in identities
                ]
            )
            if snapshot.discovery_id is not None and any(
                failure.source is None and failure.retryable for failure in snapshot.failures
            ):
                prior = await transaction.extraction.draft(
                    identifier=snapshot.discovery_id, scope=self._scope
                )
        coverage_deferred = any(
            coverage.has_deferred for draft in drafts for coverage in draft.coverage
        )
        key = hash_json(
            value=record_value(
                value=(
                    run.schema_version,
                    snapshot.id,
                    identities,
                    *((prior.id,) if prior is not None else ()),
                )
            )
        ).value
        await self._checkpoint(worker=worker, status=RunStatus.EXTRACTING)
        draft = await self._wait(
            worker=worker,
            work=extraction.extract_captured(
                actor=run.actor,
                idempotency_key=key,
                request=ExtractionRequest(
                    context=snapshot.context,
                    revisions=tuple(task.source for task in run.tasks if task.draft_id is not None),
                    prompt=snapshot.prompt,
                    schema=run.schema_json,
                    callback=None,
                    run_id=snapshot.id,
                    schema_version=run.schema_version,
                    schema_sources=drafts,
                    schema_prior=prior,
                ),
            ),
        )
        alignment = await self._wait(
            worker=worker,
            work=self._align(actor=run.actor, discovery_id=draft.id, idempotency_key=key),
        )
        errors = self._integration_failures(draft=draft, coverage_deferred=coverage_deferred)
        await self._checkpoint(
            worker=worker,
            status=RunStatus.PARTIALLY_FAILED if errors else RunStatus.RECONCILING,
            consolidated=alignment,
            modeling_errors=errors,
        )

    @staticmethod
    def _integration_failures(
        *, draft: DiscoveryDraft, coverage_deferred: bool
    ) -> tuple[DomainKernelError, ...]:
        from pydantic import TypeAdapter  # noqa: PLC0415 - Keep the public SDK import lightweight.

        errors: list[DomainKernelError] = []
        receipt = TypeAdapter(dict[str, object]).validate_json(draft.schema_review_receipt or "{}")
        if receipt.get("post_admission_pending"):
            errors.append(
                InferenceError(
                    message="The admitted draft has deferred competency-question checks.",
                    retryable=True,
                )
            )
        if receipt.get("mapping_pending"):
            errors.append(
                InferenceError(
                    message="The admitted draft has deferred reference mapping.", retryable=True
                )
            )
        if coverage_deferred:
            errors.append(
                InferenceError(
                    message="Continue deferred passage coverage before marking the draft complete.",
                    retryable=True,
                )
            )
        return tuple(errors)

    async def _ancestry(
        self, *, parent: DiscoveryRunId | None, source: SourceRevision
    ) -> tuple[DiscoveryDraft, ...]:
        if parent is None:
            return ()
        result: list[DiscoveryDraft] = []
        seen: set[DiscoveryRunId] = set()
        async with self._transaction() as transaction:
            if not isinstance(transaction, ExtractionTransaction):
                raise MissingCapabilityError(message="Configure durable extraction persistence.")
            while parent is not None:
                if parent in seen:
                    raise StaleStateError(message="Inspect the discovery continuation chain.")
                seen.add(parent)
                run = await transaction.discovery_runs.get(scope=self._scope, run_id=parent)
                task = next((task for task in run.tasks if task.source == source), None)
                if task is None or task.draft_id is None:
                    raise StaleStateError(
                        message="Reopen the exact parent draft for the continued source."
                    )
                result.append(
                    await transaction.extraction.draft(identifier=task.draft_id, scope=self._scope)
                )
                parent = run.snapshot.parent_run_id
        return tuple(result)

    async def _fail_task(
        self, *, worker: _Worker, task: SourceCheckpoint, error: DomainKernelError
    ) -> None:
        issue = error.issue if isinstance(error, InferenceError) else None
        if issue is None:
            issue = Issue(
                code=error.code, message=str(error), path=("sources", task.source.source_id.value)
            )
        failure = DiscoveryFailure(
            source_label=task.source.source_id.value,
            source=task.source,
            issue=issue,
            retryable=error.retryable,
        )
        await self._checkpoint(
            worker=worker,
            status=worker.run.snapshot.status,
            task=replace(task, failure=failure),
        )

    async def _checkpoint(  # noqa: PLR0913 - The workflow pins the request and checkpoint explicitly.
        self,
        *,
        worker: _Worker,
        status: RunStatus,
        task: SourceCheckpoint | None = None,
        report: bool = True,
        consolidated: Alignment | None = None,
        modeling_error: DomainKernelError | None = None,
        modeling_errors: tuple[DomainKernelError, ...] = (),
    ) -> None:
        current = worker.run
        updated = current.advance(status=status, task=task)
        if consolidated is not None:
            updated = replace(
                updated,
                snapshot=replace(
                    updated.snapshot,
                    discovery_id=consolidated.discovery_id,
                    reconciliation_id=consolidated.id,
                ),
            )
        errors = (*modeling_errors, *((modeling_error,) if modeling_error is not None else ()))
        for error in errors:
            failure = DiscoveryFailure(
                source_label="schema",
                source=None,
                issue=Issue(code=error.code, message=str(error), path=("schema",)),
                retryable=error.retryable,
            )
            updated = replace(
                updated,
                snapshot=replace(updated.snapshot, failures=(*updated.snapshot.failures, failure)),
            )
        async with self._transaction() as transaction:
            lease = await transaction.operations.renew(
                invocation=worker.invocation, lease=worker.lease
            )
            await transaction.discovery_runs.save(
                run=updated, expected_version=current.snapshot.version
            )
        worker.lease = lease
        worker.run = updated
        if report and worker.progress is not None:
            worker.progress(
                DiscoveryProgress(
                    scope=self._scope,
                    run_id=updated.snapshot.id,
                    stage=status,
                    completed=sum(item.draft_id is not None for item in updated.tasks),
                    total=len(updated.tasks),
                )
            )

    async def _wait[T](self, *, worker: _Worker, work: Coroutine[object, object, T]) -> T:
        async def renew() -> None:
            async with self._transaction() as transaction:
                updated = await transaction.operations.renew(
                    invocation=worker.invocation, lease=worker.lease
                )
            worker.lease = updated

        return await keep_work_leased(work=work, renew=renew, interval=_HEARTBEAT_SECONDS)

    async def _finish(self, *, worker: _Worker) -> None:
        run = worker.run
        if run.snapshot.failures:
            status = (
                RunStatus.PARTIALLY_FAILED
                if run.snapshot.reconciliation_id is not None
                or any(item.alignment_id is not None for item in run.tasks)
                else RunStatus.FAILED
            )
        else:
            status = await self._review_status(run_id=run.snapshot.id)
        await self._checkpoint(worker=worker, status=status)

    async def _review_status(self, *, run_id: DiscoveryRunId) -> RunStatus:
        async with self._transaction() as transaction:
            if not isinstance(transaction, ReviewTransaction):
                return RunStatus.NEEDS_REVIEW
            page = await transaction.reviews.list(
                scope=self._scope,
                kind=None,
                status=CaseStatus.PENDING,
                limit=1,
                cursor=None,
                run_id=run_id,
            )
            return RunStatus.NEEDS_REVIEW if page.items else RunStatus.READY_TO_PREPARE
