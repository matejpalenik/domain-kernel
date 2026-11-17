"""Store an immutable selected pack alongside the model's other SQLite state."""

from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from sqlalchemy import ForeignKeyConstraint, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.reference_packs.api.packs import ReferencePack
from domain_kernel.reference_packs.application.selection_ports import SelectedPacks
from domain_kernel.reference_packs.domain.changes import pack_pin
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.identifiers.content_hash import ContentHash

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.shared.contracts import ModelScope


@final
class SelectedPackRow(SQLiteBase):
    """Canonical pack bytes and their indexable workspace pin."""

    __tablename__ = "dk_model_pack_selection"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)
    payload: Mapped[bytes] = mapped_column(LargeBinary)


@final
class SQLiteSelectedPacks(SelectedPacks):
    """Persist and load the pack selected in the owning operation."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the model creation and review transaction."""
        self._session = session

    @override
    async def attach(self, *, scope: ModelScope, pack: ReferencePack) -> None:
        """Save the exact optional materialization within model creation."""
        self._session.add(
            SelectedPackRow(
                project_id=scope.project_id.value,
                model_id=scope.model_id.value,
                key=pack.pin.key,
                version=pack.pin.version,
                content_hash=pack.pin.content_hash.value,
                payload=pack.serialize(),
            )
        )
        await self._session.flush()

    @override
    async def get(self, *, scope: ModelScope) -> ReferencePack | None:
        """Verify the persisted canonical bytes against the selected metadata."""
        row = await self._row(scope=scope)
        if row is None:
            return None
        return self._pack(row=row)

    async def _row(self, *, scope: ModelScope) -> SelectedPackRow | None:
        return await self._session.get(
            SelectedPackRow, (scope.project_id.value, scope.model_id.value)
        )

    @staticmethod
    def _pack(*, row: SelectedPackRow) -> ReferencePack:
        pack = ReferencePack.deserialize(payload=row.payload)
        pin = ReferencePackPin(
            key=row.key,
            version=row.version,
            content_hash=ContentHash(value=row.content_hash),
        )
        if pack.pin != pin:
            raise StaleStateError(message="Restore the exact materialized workspace pack.")
        return pack

    @override
    async def replace(
        self, *, scope: ModelScope, previous: ReferencePackPin | None, pack: ReferencePack | None
    ) -> None:
        """Apply a new working selection while preserving historical review snapshots."""
        row = await self._row(scope=scope)
        current = None if row is None else self._pack(row=row)
        if pack_pin(pack=current) != previous:
            raise StaleStateError(message="Reload the current reference pack before accepting.")
        if row is None:
            if pack is not None:
                await self.attach(scope=scope, pack=pack)
        elif pack is None:
            await self._session.delete(row)
        else:
            row.payload = pack.serialize()
            row.key = pack.pin.key
            row.version = pack.pin.version
            row.content_hash = pack.pin.content_hash.value
        await self._session.flush()
