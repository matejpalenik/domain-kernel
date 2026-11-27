from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, final, override

from sqlalchemy import select

from domain_kernel.projects.application.protocols.project_catalog import ProjectCatalog
from domain_kernel.projects.domain.errors.project_already_exists_error import (
    ProjectAlreadyExistsError,
)
from domain_kernel.projects.domain.errors.project_not_found_error import ProjectNotFoundError
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.projects.domain.project_info import ProjectInfo
from domain_kernel.shared.infrastructure.persistence.rows.project_row import ProjectRow
from domain_kernel.shared.infrastructure.persistence.sql_insert import SqlInsert

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor


from domain_kernel.shared.infrastructure.persistence.catalog_pagination import CatalogPagination


@final
class SqlAlchemyProjectCatalog(ProjectCatalog):
    """Read and create project records using the current transaction."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's session."""
        self._session = session

    @override
    async def create(self, *, project: ProjectInfo) -> None:
        """Reserve the globally unique lookup name and persist the project."""
        created = await self._session.scalar(
            SqlInsert.for_session(session=self._session, row=ProjectRow)
            .values(
                id=project.id.value,
                name=project.name,
                display_name=project.display_name,
                created_at=project.created_at.isoformat(),
            )
            .on_conflict_do_nothing(index_elements=(ProjectRow.name,))
            .returning(ProjectRow.id),
        )
        if created is None:
            raise ProjectAlreadyExistsError

    @override
    async def get(self, *, name: str) -> ProjectInfo:
        """Read a project by its exact global lookup name."""
        row = await self._session.scalar(select(ProjectRow).where(ProjectRow.name == name))
        if row is None:
            raise ProjectNotFoundError

        return self._project(row=row)

    @override
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ProjectInfo]:
        """Return projects in lookup-name order using the supplied continuation."""
        scope = "projects"
        start = CatalogPagination.after_name(scope=scope, cursor=cursor, limit=limit)

        rows = await self._session.scalars(
            select(ProjectRow)
            .where(ProjectRow.name > start)
            .order_by(ProjectRow.name)
            .limit(limit + 1),
        )

        return CatalogPagination.page(
            items=tuple(self._project(row=row) for row in rows), scope=scope, limit=limit
        )

    @staticmethod
    def _project(*, row: ProjectRow) -> ProjectInfo:
        """Convert the persisted project row into detached SDK metadata."""
        return ProjectInfo(
            id=ProjectId(value=row.id),
            name=row.name,
            display_name=row.display_name,
            created_at=datetime.fromisoformat(row.created_at),
        )
