"""Capture and persist deterministic compilation inputs."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel._shared.application.persistence import Invocation, OperationOutcome
from domain_kernel._shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel._shared.domain.record_encoding import record_bytes, record_value
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.modeling.application.compilation_ports import CompiledSnapshot
from domain_kernel.modeling.application.dependencies import materialize_dependencies
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.snapshot_integrity import candidate_digest
from domain_kernel.modeling.domain.snapshots import (
    Candidate,
    ModelContent,
    ReviewSnapshot,
    VisibleQuestion,
)
from domain_kernel.reference_packs.domain.dispositions import active_dispositions
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.occurrences import alignments_at_revision
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
    from domain_kernel.modeling.application.dependencies import PublishedDependencies
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.reference_packs.application.selection_ports import SelectedPacks
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
        packs: SelectedPacks | None = None,
        resolver: PublishedDependencies | None = None,
    ) -> None:
        """Bind the shared operation resources."""
        self._models = models
        self._definitions = definitions
        self._reviews = reviews
        self._compilation = compilation
        self._audit = audit
        self._operations = operations
        self._transaction = transaction
        self._packs = packs
        self._resolver = resolver

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
        pack = None if self._packs is None else await self._packs.get(scope=current.scope)
        if current.reference_pack != (None if pack is None else pack.pin):
            raise StaleStateError(message="Materialize the exact selected pack before compiling")
        active = tuple(item for item in definitions if item.status is DefinitionStatus.APPROVED)
        content = ModelContent(
            definitions=active,
            source_alignments=alignments_at_revision(decisions=decisions, definitions=active),
            reference_dispositions=active_dispositions(
                definitions=active,
                decisions=decisions,
                pack=current.reference_pack,
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
                case.status in (CaseStatus.PENDING, CaseStatus.DEFERRED)
                and case.grouped_by_case_id is None
                for case in cases
            ),
            questions=tuple(
                VisibleQuestion(
                    id=question.id,
                    text=question.text,
                    scope_text=question.scope_text,
                    rationale=question.rationale,
                    reviewer=question.reviewer,
                    decision_id=question.decision_id,
                )
                for case in cases
                if case.status is CaseStatus.REVIEWED_NONBLOCKING
                and (question := case.question) is not None
                and question.rationale is not None
                and question.reviewer is not None
                and question.decision_id is not None
            ),
        )
        candidate = Candidate(
            id=CandidateId(value=uuid4().hex),
            scope=current.scope,
            kind=current.kind,
            description=current.description,
            workspace_revision=current.revision,
            review_snapshot_version=review.version,
            review_snapshot_hash=review.content_hash,
            content_hash=review.content_hash,
            content=content,
            reference_pack=current.reference_pack,
            baseline=current.baseline,
            dependencies=current.dependencies,
            dependency_bundles=await materialize_dependencies(
                resolver=self._resolver,
                scope=current.scope,
                pins=current.dependencies,
            ),
            decisions=decisions,
            nonblocking_questions=review.questions,
        )
        return CompiledSnapshot(
            candidate=replace(candidate, content_hash=candidate_digest(candidate=candidate)),
            review=review,
            reference_pack=pack,
        )

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
