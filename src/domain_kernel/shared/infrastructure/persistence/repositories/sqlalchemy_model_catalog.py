from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, final, override

from sqlalchemy import select

from domain_kernel.modeling.application.protocols.model_catalog import ModelCatalog
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.modeling.domain.errors.model_already_exists_error import ModelAlreadyExistsError
from domain_kernel.modeling.domain.errors.model_not_found_error import ModelNotFoundError
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.modeling.domain.models import ModelInfo, ReferencePackPin
from domain_kernel.modeling.infrastructure.sqlite_baselines import SQLiteBaseline
from domain_kernel.modeling.infrastructure.sqlite_dependencies import SQLiteDependencyPins
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.reference_packs.infrastructure.sqlite_selection import SelectedPackRow
from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.infrastructure.persistence.rows.model_row import ModelRow
from domain_kernel.shared.infrastructure.persistence.sql_insert import SqlInsert

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor
    from domain_kernel.shared.domain.value_objects.model_version import ModelVersion

from domain_kernel.shared.infrastructure.persistence.catalog_pagination import CatalogPagination


@final
class SqlAlchemyModelCatalog(ModelCatalog):
    """Read and create model workspaces without implicit pack or baseline selection."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's session."""
        self._session = session
        self._dependencies = SQLiteDependencyPins(session=session)
        self._baselines = SQLiteBaseline(session=session)

    async def _inspect(
        self,
        *,
        row: ModelRow,
        key: str | None,
        version: str | None,
        digest: str | None,
    ) -> ModelInfo:
        """Load the selected pack, dependencies and baseline for this model."""
        scope = ModelScope(
            project_id=ProjectId(value=row.project_id), model_id=ModelId(value=row.id)
        )

        pack = None
        if key is not None and version is not None and digest is not None:
            pack = ReferencePackPin(
                key=key, version=version, content_hash=ContentHash(value=digest)
            )

        return self._model(
            row=row,
            pack=pack,
            dependencies=await self._dependencies.pins(scope=scope),
            baseline=await self._baselines.get(scope=scope),
        )

    @override
    async def create(self, *, info: ModelInfo) -> None:
        """Reserve the model's project-local name and persist its initial metadata."""
        created = await self._session.scalar(
            SqlInsert.for_session(session=self._session, row=ModelRow)
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

        if info.baseline is not None:
            await self._baselines.attach(scope=info.scope, pin=info.baseline)

        if info.dependencies:
            await self._dependencies.attach(scope=info.scope, pins=info.dependencies)

    @override
    async def get(self, *, project_id: ProjectId, name: str) -> ModelInfo:
        """Read a model's metadata by exact project and lookup name."""
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

        return await self._inspect(row=row, key=key, version=version, digest=digest)

    @override
    async def list(
        self,
        *,
        project_id: ProjectId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[ModelInfo]:
        """Page through one project's model metadata in lookup-name order."""
        scope = Hashing.hash_json(value=["models", project_id.value]).value
        start = CatalogPagination.after_name(scope=scope, cursor=cursor, limit=limit)

        rows = await self._session.execute(
            select(
                ModelRow, SelectedPackRow.key, SelectedPackRow.version, SelectedPackRow.content_hash
            )
            .outerjoin(SelectedPackRow)
            .where(ModelRow.project_id == project_id.value, ModelRow.name > start)
            .order_by(ModelRow.name)
            .limit(limit + 1),
        )

        return CatalogPagination.page(
            items=[
                await self._inspect(row=row, key=key, version=version, digest=digest)
                for row, key, version, digest in rows
            ],
            scope=scope,
            limit=limit,
        )

    @staticmethod
    def _model(
        *,
        row: ModelRow,
        pack: ReferencePackPin | None,
        dependencies: Sequence[ModelVersion],
        baseline: ModelVersion | None,
    ) -> ModelInfo:
        """Build a detached model snapshot from its row and exact pinned resources."""
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
            reference_pack=pack,
            dependencies=dependencies,
            baseline=baseline,
        )
