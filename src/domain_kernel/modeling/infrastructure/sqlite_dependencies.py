"""Store ordered same-project release selections in SQLite."""

from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from sqlalchemy import ForeignKeyConstraint, Integer, String, UniqueConstraint, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.modeling.application.dependencies import WritableDependencyPins
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.shared.contracts import ModelScope, ModelVersion
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.infrastructure.sqlite_base import SQLiteBase

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


@final
class _DependencyRow(SQLiteBase):
    __tablename__ = "dk_model_dependency"
    __table_args__: tuple[ForeignKeyConstraint | UniqueConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
        ForeignKeyConstraint(
            ["project_id", "source_model_id", "version"],
            ["dk_bundle.project_id", "dk_bundle.model_id", "dk_bundle.version"],
        ),
        UniqueConstraint("project_id", "model_id", "source_model_id"),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_model_id: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)


@final
class SQLiteDependencyPins(WritableDependencyPins):
    """Read exact selections and attach validated pins on model creation."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the current operation's session."""
        self._session = session

    async def attach(self, *, scope: ModelScope, pins: Sequence[ModelVersion]) -> None:
        """Save the order and hashes of an already verified selection."""
        self._session.add_all(
            _DependencyRow(
                project_id=scope.project_id.value,
                model_id=scope.model_id.value,
                position=position,
                source_model_id=pin.scope.model_id.value,
                version=pin.version,
                content_hash=pin.content_hash.value,
            )
            for position, pin in enumerate(pins)
        )
        await self._session.flush()

    @override
    async def pins(self, *, scope: ModelScope) -> tuple[ModelVersion, ...]:
        matches = await self._session.scalars(
            select(_DependencyRow)
            .where(
                _DependencyRow.project_id == scope.project_id.value,
                _DependencyRow.model_id == scope.model_id.value,
            )
            .order_by(_DependencyRow.position)
        )
        return tuple(
            ModelVersion(
                scope=ModelScope(
                    project_id=scope.project_id,
                    model_id=ModelId(value=row.source_model_id),
                ),
                version=row.version,
                content_hash=ContentHash(value=row.content_hash),
            )
            for row in matches
        )

    @override
    async def replace(
        self,
        *,
        scope: ModelScope,
        before: Sequence[ModelVersion],
        after: Sequence[ModelVersion],
    ) -> None:
        if await self.pins(scope=scope) != before:
            raise StaleStateError(message="Reload and inspect the workspace's selected releases")
        _ = await self._session.execute(
            delete(_DependencyRow).where(
                _DependencyRow.project_id == scope.project_id.value,
                _DependencyRow.model_id == scope.model_id.value,
            ),
        )
        await self.attach(scope=scope, pins=after)
