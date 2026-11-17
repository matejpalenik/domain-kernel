"""Persist project and model catalogs with typed SQLite expressions."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from typing import TYPE_CHECKING, final, override

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from domain_kernel._shared.application.catalogs import ModelCatalog, ProjectCatalog
from domain_kernel._shared.domain.naming import require_lookup_name
from domain_kernel._shared.infrastructure.sqlite_workspaces import ModelRow, ProjectRow
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.modeling.domain.errors.model_already_exists_error import ModelAlreadyExistsError
from domain_kernel.modeling.domain.errors.model_not_found_error import ModelNotFoundError
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.modeling.domain.models import ModelInfo, ReferencePackPin
from domain_kernel.projects.domain.errors.project_already_exists_error import (
    ProjectAlreadyExistsError,
)
from domain_kernel.projects.domain.errors.project_not_found_error import ProjectNotFoundError
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.projects.domain.project_info import ProjectInfo
from domain_kernel.reference_packs.infrastructure.sqlite_selection import SelectedPackRow
from domain_kernel.shared.contracts import ModelScope, Page
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


def _offset(*, scope: str, cursor: PageCursor | None, limit: int) -> str:
    if type(limit) is not int or limit < 1:
        raise ValueError("Catalog page limit must be a positive integer")
    if cursor is None:
        return ""
    try:
        binding, name = urlsafe_b64decode(cursor.value).decode("ascii").split(",")
        if binding == scope:
            require_lookup_name(name=name)
            return name
    except ValueError:
        pass
    raise ValueError("Use a cursor returned by the same catalog query")


def _page[T: ProjectInfo | ModelInfo](*, items: Sequence[T], scope: str, limit: int) -> Page[T]:
    selected = items[:limit]
    cursor = None
    if len(items) > limit:
        token = urlsafe_b64encode(f"{scope},{selected[-1].name}".encode("ascii")).decode("ascii")
        cursor = PageCursor(value=token)
    return Page(items=selected, next_cursor=cursor)


def _project(*, row: ProjectRow) -> ProjectInfo:
    return ProjectInfo(
        id=ProjectId(value=row.id),
        name=row.name,
        display_name=row.display_name,
        created_at=datetime.fromisoformat(row.created_at),
    )


def _model(
    *,
    row: ModelRow,
    key: str | None,
    version: str | None,
    digest: str | None,
) -> ModelInfo:
    pin = None
    if key is not None and version is not None and digest is not None:
        pin = ReferencePackPin(key=key, version=version, content_hash=ContentHash(value=digest))
    return ModelInfo(
        scope=ModelScope(
            project_id=ProjectId(value=row.project_id),
            model_id=ModelId(value=row.id),
        ),
        name=row.name,
        display_name=row.display_name,
        description=row.description,
        kind=ModelKind(row.kind),
        created_at=datetime.fromisoformat(row.created_at),
        revision=row.revision,
        reference_pack=pin,
    )


@final
class SQLiteProjectCatalog(ProjectCatalog):
    """Read and create project records using the current transaction."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's session."""
        self._session = session

    @override
    async def create(self, *, project: ProjectInfo) -> None:
        created = await self._session.scalar(
            insert(ProjectRow)
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
        row = await self._session.scalar(select(ProjectRow).where(ProjectRow.name == name))
        if row is None:
            raise ProjectNotFoundError
        return _project(row=row)

    @override
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ProjectInfo]:
        scope = "projects"
        start = _offset(scope=scope, cursor=cursor, limit=limit)
        rows = await self._session.scalars(
            select(ProjectRow)
            .where(ProjectRow.name > start)
            .order_by(ProjectRow.name)
            .limit(limit + 1),
        )
        return _page(items=tuple(_project(row=row) for row in rows), scope=scope, limit=limit)


@final
class SQLiteModelCatalog(ModelCatalog):
    """Read and create model workspaces without implicit pack or baseline selection."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's session."""
        self._session = session

    @override
    async def create(self, *, info: ModelInfo) -> None:
        created = await self._session.scalar(
            insert(ModelRow)
            .values(
                project_id=info.scope.project_id.value,
                id=info.scope.model_id.value,
                name=info.name,
                display_name=info.display_name,
                description=info.description,
                kind=info.kind.value,
                revision=info.revision,
                created_at=info.created_at.isoformat(),
            )
            .on_conflict_do_nothing(index_elements=(ModelRow.project_id, ModelRow.name))
            .returning(ModelRow.id),
        )
        if created is None:
            raise ModelAlreadyExistsError

    @override
    async def get(self, *, project_id: ProjectId, name: str) -> ModelInfo:
        result = await self._session.execute(
            select(
                ModelRow, SelectedPackRow.key, SelectedPackRow.version, SelectedPackRow.content_hash
            )
            .outerjoin(SelectedPackRow)
            .where(
                ModelRow.project_id == project_id.value,
                ModelRow.name == name,
            ),
        )
        match = result.first()
        if match is None:
            raise ModelNotFoundError
        row, key, version, digest = match
        return _model(row=row, key=key, version=version, digest=digest)

    @override
    async def list(
        self,
        *,
        project_id: ProjectId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[ModelInfo]:
        scope = hash_json(value=["models", project_id.value]).value
        start = _offset(scope=scope, cursor=cursor, limit=limit)
        rows = await self._session.execute(
            select(
                ModelRow, SelectedPackRow.key, SelectedPackRow.version, SelectedPackRow.content_hash
            )
            .outerjoin(SelectedPackRow)
            .where(ModelRow.project_id == project_id.value, ModelRow.name > start)
            .order_by(ModelRow.name)
            .limit(limit + 1),
        )
        return _page(
            items=tuple(
                _model(row=row, key=key, version=version, digest=digest)
                for row, key, version, digest in rows
            ),
            scope=scope,
            limit=limit,
        )
