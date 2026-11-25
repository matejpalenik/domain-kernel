"""Store a workspace's exact direct-baseline publication pin."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from sqlalchemy import ForeignKeyConstraint, String, select
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.shared.contracts import ModelScope, ModelVersion
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.infrastructure.sqlite_base import SQLiteBase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@final
class _BaselineRow(SQLiteBase):
    __tablename__ = "dk_model_baseline"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
        ForeignKeyConstraint(
            ["project_id", "source_model_id", "version"],
            ["dk_bundle.project_id", "dk_bundle.model_id", "dk_bundle.version"],
        ),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_model_id: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)


@final
class SQLiteBaseline:
    """Read and attach immutable baseline provenance in the active operation."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's session."""
        self._session = session

    async def attach(self, *, scope: ModelScope, pin: ModelVersion) -> None:
        """Record the registered source of a newly created workspace."""
        self._session.add(
            _BaselineRow(
                project_id=scope.project_id.value,
                model_id=scope.model_id.value,
                source_model_id=pin.scope.model_id.value,
                version=pin.version,
                content_hash=pin.content_hash.value,
            )
        )
        await self._session.flush()

    async def get(self, *, scope: ModelScope) -> ModelVersion | None:
        """Read a detached pin without loading the original publication."""
        row = await self._session.scalar(
            select(_BaselineRow).where(
                _BaselineRow.project_id == scope.project_id.value,
                _BaselineRow.model_id == scope.model_id.value,
            ),
        )
        if row is None:
            return None
        return ModelVersion(
            scope=ModelScope(
                project_id=scope.project_id, model_id=ModelId(value=row.source_model_id)
            ),
            version=row.version,
            content_hash=ContentHash(value=row.content_hash),
        )
