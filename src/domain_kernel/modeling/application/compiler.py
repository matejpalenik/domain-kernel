"""Capture and persist deterministic compilation inputs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel._shared.application.persistence import Invocation, OperationOutcome
from domain_kernel._shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel._shared.domain.record_encoding import record_bytes, record_value
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.modeling.application.compilation_ports import CompiledSnapshot
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.snapshots import Candidate, ModelContent, ReviewSnapshot
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validation import require_text

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from domain_kernel._shared.application.catalogs import ModelCatalog
    from domain_kernel._shared.application.persistence import (
        AuditRepository,
        IdempotencyRepository,
        TransactionManager,
    )
    from domain_kernel.modeling.application.compilation_ports import CompilationRepository
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.review.application.ports import DefinitionRepository, ReviewRepository
    from domain_kernel.review.domain.models import DecisionRecord
    from domain_kernel.shared.contracts import Page
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


async def _capture_pages[T](
    *,
    load: Callable[[PageCursor | None], Awaitable[Page[T]]],
) -> tuple[T, ...]:
    items: list[T] = []
    cursor = None
    while True:
        page = await load(cursor)
        items.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            return tuple(items)


@final
class ModelCompiler:
    """Capture exact domain values from one operation and persist their candidate."""

    def __init__(  # noqa: PLR0913 - Inject the collaborators used by this operation.
        self,
        *,
        models: ModelCatalog,
        definitions: DefinitionRepository,
        reviews: ReviewRepository,
        compilation: CompilationRepository,
        audit: AuditRepository,
        operations: IdempotencyRepository,
        transaction: TransactionManager,
    ) -> None:
        """Bind the shared operation resources."""
        self._models = models
        self._definitions = definitions
        self._reviews = reviews
        self._compilation = compilation
        self._audit = audit
        self._operations = operations
        self._transaction = transaction

    async def capture(self, *, model: ModelInfo) -> CompiledSnapshot:
        """Materialize immutable inputs inside the caller's active transaction."""
        current = await self._models.get(project_id=model.scope.project_id, name=model.name)
        if current.scope != model.scope:
            raise StaleStateError(message="Reopen the exact workspace before compiling")
        definitions = await _capture_pages(
            load=lambda cursor: self._definitions.list(
                scope=model.scope,
                status=None,
                limit=100,
                cursor=cursor,
            )
        )
        cases = await _capture_pages(
            load=lambda cursor: self._reviews.list(
                scope=model.scope,
                kind=None,
                status=None,
                limit=100,
                cursor=cursor,
            )
        )
        decisions: list[DecisionRecord] = []
        for case in cases:
            decisions.extend(
                await _capture_pages(
                    load=lambda cursor, case=case: self._reviews.history(
                        scope=model.scope,
                        case_id=case.id,
                        limit=100,
                        cursor=cursor,
                    )
                )
            )
        content = ModelContent(
            definitions=tuple(
                item for item in definitions if item.status is DefinitionStatus.APPROVED
            ),
            retired_definitions=tuple(
                item for item in definitions if item.status is DefinitionStatus.RETIRED
            ),
        )
        review = ReviewSnapshot(
            scope=current.scope,
            version=sum(case.version for case in cases),
            content_hash=hash_json(value=record_value(value=(cases, decisions))),
            decisions=decisions,
            pending_required=sum(
                case.status is CaseStatus.PENDING and case.grouped_by_case_id is None
                for case in cases
            ),
        )
        content_hash = hash_json(
            value=record_value(
                value=(
                    "candidate-v1",
                    current.scope,
                    current.kind,
                    current.description,
                    current.revision,
                    current.reference_pack,
                    current.baseline,
                    current.dependencies,
                    content,
                    review.version,
                    review.content_hash,
                )
            )
        )
        candidate = Candidate(
            id=CandidateId(value=uuid4().hex),
            scope=current.scope,
            kind=current.kind,
            description=current.description,
            workspace_revision=current.revision,
            review_snapshot_version=review.version,
            review_snapshot_hash=review.content_hash,
            content_hash=content_hash,
            content=content,
            reference_pack=current.reference_pack,
            baseline=current.baseline,
            dependencies=current.dependencies,
            decisions=decisions,
            nonblocking_questions=review.questions,
        )
        return CompiledSnapshot(candidate=candidate, review=review)

    async def compile(self, *, model: ModelInfo, actor: str) -> Candidate:
        """Persist the captured candidate with its host-attributed audit event."""
        require_text(value=actor, field="Actor")
        request = Invocation.resolve(
            project_id=model.scope.project_id,
            model_id=model.scope.model_id,
            operation="compile",
            actor=actor,
            key=None,
            intent=model.scope.model_id.value,
        )
        async with self._transaction.begin():
            # Claim takes the SQLite writer gate before the transaction reads workspace state.
            lease = await self._operations.claim(invocation=request, owner=uuid4().hex)
            if isinstance(lease, OperationOutcome):
                return (
                    await self._compilation.get_candidate(
                        scope=model.scope,
                        candidate_id=CandidateId(value=lease.resource_id),
                    )
                ).candidate
            snapshot = await self.capture(model=model)
            await self._compilation.add_candidate(snapshot=snapshot)
            candidate = snapshot.candidate
            await self._audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=model.scope.project_id,
                    model_id=model.scope.model_id,
                    action=AuditAction.COMPILE,
                    outcome=AuditOutcome.SUCCEEDED,
                    actor=actor,
                    recorded_at=datetime.now(tz=UTC),
                    before=(),
                    after=(
                        AuditResource(
                            resource_id=candidate.id,
                            revision=None,
                            content_hash=hash_bytes(content=record_bytes(value=candidate)),
                        ),
                    ),
                )
            )
            await self._operations.complete(
                invocation=request,
                lease=lease,
                outcome=OperationOutcome(resource_kind="candidate", resource_id=candidate.id.value),
            )
            return candidate
