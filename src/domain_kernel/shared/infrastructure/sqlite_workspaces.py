"""Store workspace identity and guard model revision transitions in SQLite."""

from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    select,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.modeling.domain.errors.model_not_found_error import ModelNotFoundError
from domain_kernel.shared.application.persistence import WorkspaceRevisions
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.shared.validation import require_exact

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.shared.contracts import ModelScope


@final
class ProjectRow(SQLiteBase):
    """Persist the project's stable identity and initial catalog metadata."""

    __tablename__ = "dk_project"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


@final
class ModelRow(SQLiteBase):
    """Persist the scoped workspace and its current revision."""

    __tablename__ = "dk_model"
    __table_args__: tuple[UniqueConstraint | CheckConstraint, ...] = (
        UniqueConstraint("project_id", "name", name="dk_model_scoped_name"),
        CheckConstraint("revision >= 0", name="dk_model_nonnegative_revision"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("dk_project.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)


@final
class SQLiteWorkspaceRevisions(WorkspaceRevisions):
    """Compare and advance a persisted workspace revision within the caller's transaction."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation-local session."""
        self._session = session

    @override
    async def revision(self, *, scope: ModelScope) -> int:
        value = await self._session.scalar(
            select(ModelRow.revision).where(
                ModelRow.project_id == scope.project_id.value,
                ModelRow.id == scope.model_id.value,
            )
        )
        if value is None:
            raise ModelNotFoundError
        return value

    @override
    async def advance(self, *, scope: ModelScope, expected_revision: int) -> None:
        require_exact(value=expected_revision, expected=int, field="Expected workspace revision")
        if expected_revision < 0:
            raise ValueError("Expected workspace revision must be nonnegative")
        value = await self._session.scalar(
            update(ModelRow)
            .where(
                ModelRow.project_id == scope.project_id.value,
                ModelRow.id == scope.model_id.value,
                ModelRow.revision == expected_revision,
            )
            .values(revision=ModelRow.revision + 1)
            .returning(ModelRow.revision)
        )
        if value is None:
            raise StaleStateError
