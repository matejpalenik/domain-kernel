"""Public handle for a scoped project and its model workspaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from domain_kernel._composition import open_models
from domain_kernel.modeling.api.model import Model

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.application.catalogs import CatalogTransaction
    from domain_kernel._shared.application.persistence import UnitOfWorkFactory
    from domain_kernel._shared.domain.audit import AuditRecord
    from domain_kernel.bundles import DomainModelBundle
    from domain_kernel.modeling.domain.enums.model_kind import ModelKind
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.modeling.domain.snapshots import PublicationRules
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.projects.domain.project_info import ProjectInfo
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.contracts import ModelVersion, Page
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


@final
class Project:
    """Access a project's named modeling workspaces and durable audit history."""

    def __init__(
        self,
        *,
        info: ProjectInfo,
        resources: UnitOfWorkFactory[CatalogTransaction],
        publication_rules: PublicationRules,
    ) -> None:
        """Bind loaded project identity to the client's resource factory."""
        self._info = info
        self._resources = resources
        self._publication_rules = publication_rules

    @property
    def id(self) -> ProjectId:
        """Return the project's immutable identity."""
        return self._info.id

    @property
    def name(self) -> str:
        """Return the exact lookup name."""
        return self._info.name

    @property
    def display_name(self) -> str:
        """Return the label captured for this handle."""
        return self._info.display_name

    async def create_model(  # noqa: PLR0913 - Explicit public intent and stable names.
        self,
        *,
        actor: str,
        kind: ModelKind,
        description: str,
        display_name: str | None = None,
        name: str | None = None,
        reference_pack: ReferencePack | None = None,
        copy_from: DomainModelBundle | None = None,
        dependencies: Sequence[ModelVersion] = (),
    ) -> Model:
        """Create an independent work area for the specified modeling intent."""
        async with open_models(resources=self._resources, project_id=self.id) as models:
            info = await models.create(
                actor=actor,
                kind=kind,
                reference_pack=reference_pack,
                copy_from=copy_from,
                dependencies=dependencies,
                description=description,
                display_name=display_name,
                name=name,
            )
        return Model(
            info=info, resources=self._resources, publication_rules=self._publication_rules
        )

    async def get_model(self, *, name: str) -> Model:
        """Reopen a model by its exact project-local name."""
        async with open_models(resources=self._resources, project_id=self.id) as models:
            info = await models.get(name=name)
        return Model(
            info=info, resources=self._resources, publication_rules=self._publication_rules
        )

    async def list_models(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[ModelInfo]:
        """Page through this project's model metadata."""
        async with open_models(resources=self._resources, project_id=self.id) as models:
            return await models.list(limit=limit, cursor=cursor)

    async def get_audit_history(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[AuditRecord]:
        """Inspect attributed events across this project and its models."""
        async with self._resources() as transaction, transaction.begin():
            return await transaction.audit.list(
                project_id=self.id,
                model_id=None,
                limit=limit,
                cursor=cursor,
            )
