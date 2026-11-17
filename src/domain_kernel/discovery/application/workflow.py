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
from domain_kernel.review.application.ports import ReviewTransaction
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import (
    DomainKernelError,
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
    from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
    from domain_kernel.discovery.domain.models import InterpretationContext, ProgressCallback
    from domain_kernel.reconciliation.domain.models import Alignment
    from domain_kernel.shared.contracts import ModelScope, Page
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

    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[DiscoveryResult]:
        """Page through this workspace's persisted runs."""
        async with self._transaction() as transaction:
            return await transaction.discovery_runs.list(
                scope=self._scope, limit=limit, cursor=cursor
            )

    async def discover(  # noqa: PLR0913 - Request identity and explicit prompt inputs.
        self,
        *,
        actor: str,
        context: InterpretationContext,
        sources: Sequence[SourceRevision],
        additional_instructions: str | None,
        prompt_override: str | None,
        idempotency_key: str | None,
        on_progress: ProgressCallback | None,
    ) -> DiscoveryResult:
        """Register discovery intent before performing any inference or review preparation."""
        if self._extraction is None:
            raise MissingCapabilityError(
                message="Configure a model gateway to discover source meanings."
            )
        from domain_kernel.discovery.application.structured_output import (  # noqa: PLC0415 - Only inference needs Pydantic.
            response_schema,
        )

        revisions = snapshot_sequence(
            items=sources, item_type=SourceRevision, field="Source revisions"
        )
        if not revisions or len(set(revisions)) != len(revisions):
            raise ValueError("Select distinct exact ingested source revisions.")
        if any(item.project_id != self._scope.project_id for item in revisions):
            raise ScopeMismatchError
        schema = response_schema()
        prompt = capture_prompt(
            additional_instructions=additional_instructions,
            prompt_override=prompt_override,
            schema_json=schema,
        )
        request = Invocation.resolve(
            project_id=self._scope.project_id,
            model_id=self._scope.model_id,
            operation="discover",
            actor=actor,
            key=idempotency_key,
            intent=record_value(value=(revisions, additional_instructions, prompt_override)),
        )
        run = await self._register(
            request=request,
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
            ),
        )
        if run.snapshot.status in _IN_FLIGHT:
            return await self._advance(run=run, on_progress=on_progress)
        return run.snapshot

    async def _register(self, *, request: Invocation, new: DiscoveryRun) -> DiscoveryRun:
        async with self._transaction() as transaction:
            claim = await transaction.operations.claim(invocation=request, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                return await self._restore_outcome(transaction=transaction, outcome=claim)
            await transaction.discovery_runs.add(run=new)
            await self._audit(
                transaction=transaction, run=new, actor=request.actor, action=AuditAction.DISCOVER
            )
            await transaction.operations.complete(
                invocation=request,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="discovery_run", resource_id=new.snapshot.id.value
                ),
            )
            return new

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
            if current.snapshot.status in (RunStatus.NEEDS_REVIEW, RunStatus.READY_TO_PREPARE):
                await transaction.operations.release(invocation=invocation, lease=lease)
                return current.snapshot
        worker = _Worker(invocation=invocation, lease=lease, run=current, progress=on_progress)
        try:
            for task in current.tasks:
                if task.alignment_id is None:
                    await self._run_task(worker=worker, task=task, extraction=self._extraction)
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
        from domain_kernel.discovery.application.extraction import (  # noqa: PLC0415 - Keep read-only discovery adapter-free.
            ExtractionRequest,
        )

        run = worker.run
        snapshot = run.snapshot
        key = hash_json(value=record_value(value=(snapshot.id, task.source))).value
        draft_id = task.draft_id
        if draft_id is None:
            await self._checkpoint(worker=worker, status=RunStatus.EXTRACTING)
            try:
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
                        ),
                    ),
                )
            except DomainKernelError as error:
                await self._fail_task(worker=worker, task=task, error=error)
                return
            draft_id = draft.id
            task = replace(task, draft_id=draft_id, failure=None)
        await self._checkpoint(worker=worker, status=RunStatus.RECONCILING, task=task)
        try:
            alignment = await self._wait(
                worker=worker,
                work=self._align(actor=run.actor, discovery_id=draft_id, idempotency_key=key),
            )
        except DomainKernelError as error:
            await self._fail_task(worker=worker, task=task, error=error)
            return
        await self._checkpoint(
            worker=worker,
            status=RunStatus.RECONCILING,
            task=replace(task, alignment_id=alignment.id, failure=None),
        )

    async def _fail_task(
        self, *, worker: _Worker, task: SourceCheckpoint, error: DomainKernelError
    ) -> None:
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

    async def _checkpoint(
        self,
        *,
        worker: _Worker,
        status: RunStatus,
        task: SourceCheckpoint | None = None,
        report: bool = True,
    ) -> None:
        current = worker.run
        updated = current.advance(status=status, task=task)
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
                    completed=sum(item.alignment_id is not None for item in updated.tasks),
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
                if any(item.alignment_id is not None for item in run.tasks)
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
