"""Persist exact extraction snapshots and their typed drafts in SQLite."""

from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from sqlalchemy import ForeignKeyConstraint, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.discovery.application.ports import ExtractionRepository
from domain_kernel.discovery.domain.models import DiscoveryDraft
from domain_kernel.shared.errors import StaleStateError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
    from domain_kernel.discovery.domain.models import ExtractionIntent
    from domain_kernel.shared.contracts import ModelScope


@final
class _ExtractionRow(SQLiteBase):
    __tablename__ = "dk_extraction"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    identity: Mapped[str] = mapped_column(String, primary_key=True)
    intent: Mapped[bytes] = mapped_column(LargeBinary)
    result: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


@final
class SQLiteExtraction(ExtractionRepository):
    """Use an operation-local session for exact scoped drafts."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind a shared session without opening a transaction."""
        self._session = session

    @override
    async def reserve(self, *, intent: ExtractionIntent) -> None:
        scope = intent.context.scope
        self._session.add(
            _ExtractionRow(
                project_id=scope.project_id.value,
                model_id=scope.model_id.value,
                identity=intent.id.value,
                intent=record_bytes(value=intent),
                result=None,
            ),
        )
        await self._session.flush()

    @override
    async def complete(self, *, draft: DiscoveryDraft) -> None:
        saved = await self._row(identifier=draft.id, scope=draft.scope)
        if saved is None or saved.result is not None:
            raise StaleStateError(message="Reload the exact pending extraction capture.")
        saved.result = record_bytes(value=draft)
        await self._session.flush()

    @override
    async def draft(self, *, identifier: DiscoveryDraftId, scope: ModelScope) -> DiscoveryDraft:
        saved = await self._row(identifier=identifier, scope=scope)
        if saved is None or saved.result is None:
            raise StaleStateError(message="Reload a completed extraction capture.")
        return read_record(content=saved.result, expected=DiscoveryDraft)

    async def _row(
        self,
        *,
        identifier: DiscoveryDraftId,
        scope: ModelScope,
    ) -> _ExtractionRow | None:
        return await self._session.get(
            _ExtractionRow,
            (scope.project_id.value, scope.model_id.value, identifier.value),
        )
