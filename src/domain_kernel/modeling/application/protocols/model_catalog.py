from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor


class ModelCatalog(Protocol, metaclass=ABCMeta):
    """Persist and look up models inside one project."""

    @abstractmethod
    async def create(self, *, info: ModelInfo) -> None:
        """Add one model by its project-local name."""

    @abstractmethod
    async def get(self, *, project_id: ProjectId, name: str) -> ModelInfo:
        """Find a model by its exact scoped name."""

    @abstractmethod
    async def list(
        self,
        *,
        project_id: ProjectId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[ModelInfo]:
        """Page through one project's models by name."""
