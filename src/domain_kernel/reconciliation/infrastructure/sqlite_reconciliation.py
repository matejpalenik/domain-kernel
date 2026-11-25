"""Store prepared scoped alignments in the review transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from sqlalchemy import ForeignKeyConstraint, LargeBinary, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.reconciliation.application.ports import ReconciliationRepository
from domain_kernel.reconciliation.domain.models import Alignment
from domain_kernel.shared.domain.codecs.record_encoding import read_record, record_bytes
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.infrastructure.sqlite_base import SQLiteBase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
    from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
    from domain_kernel.shared.contracts import ModelScope


@final
class _AlignmentRow(SQLiteBase):
    __tablename__ = "dk_reconciliation"
    __table_args__: tuple[ForeignKeyConstraint | UniqueConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
        UniqueConstraint("project_id", "model_id", "draft_id", name="dk_reconciliation_draft"),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    draft_id: Mapped[str] = mapped_column(String)
    content: Mapped[bytes] = mapped_column(LargeBinary)


@final
class SQLiteReconciliation(ReconciliationRepository):
    """Read exact alignments without loading the evidence bytes or a provider."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the current session."""
        self._session = session

    @override
    async def get(self, *, scope: ModelScope, alignment_id: AlignmentId) -> Alignment:
        payload = await self._session.scalar(
            select(_AlignmentRow.content).where(
                _AlignmentRow.project_id == scope.project_id.value,
                _AlignmentRow.model_id == scope.model_id.value,
                _AlignmentRow.id == alignment_id.value,
            )
        )
        if payload is None:
            raise StaleStateError(message="Open a prepared alignment from this model.")
        return read_record(content=payload, expected=Alignment)

    @override
    async def for_draft(
        self, *, scope: ModelScope, discovery_id: DiscoveryDraftId
    ) -> Alignment | None:
        payload = await self._session.scalar(
            select(_AlignmentRow.content).where(
                _AlignmentRow.project_id == scope.project_id.value,
                _AlignmentRow.model_id == scope.model_id.value,
                _AlignmentRow.draft_id == discovery_id.value,
            )
        )
        return None if payload is None else read_record(content=payload, expected=Alignment)

    @override
    async def add(self, *, alignment: Alignment) -> None:
        self._session.add(
            _AlignmentRow(
                project_id=alignment.scope.project_id.value,
                model_id=alignment.scope.model_id.value,
                id=alignment.id.value,
                draft_id=alignment.discovery_id.value,
                content=record_bytes(value=alignment),
            )
        )
        await self._session.flush()
