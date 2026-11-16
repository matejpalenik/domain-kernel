"""Public handle for an independently managed model workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from domain_kernel._shared.application.catalogs import CatalogTransaction
    from domain_kernel._shared.application.persistence import UnitOfWorkFactory
    from domain_kernel._shared.domain.audit import AuditRecord
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.shared.contracts import ModelScope, Page
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


@final
class Model:
    """Read the model's captured metadata and attributed history."""

    def __init__(
        self,
        *,
        info: ModelInfo,
        resources: UnitOfWorkFactory[CatalogTransaction],
    ) -> None:
        """Bind a detached metadata snapshot to the client's resource factory."""
        self._info = info
        self._resources = resources

    @property
    def info(self) -> ModelInfo:
        """Return the loaded metadata without querying the workspace."""
        return self._info

    @property
    def scope(self) -> ModelScope:
        """Return the stable project and model IDs."""
        return self._info.scope

    async def get_audit_history(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[AuditRecord]:
        """Inspect durable events for this model."""
        async with self._resources() as transaction, transaction.begin():
            return await transaction.audit.list(
                project_id=self.scope.project_id,
                model_id=self.scope.model_id,
                limit=limit,
                cursor=cursor,
            )
