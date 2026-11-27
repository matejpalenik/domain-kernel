from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.projects.domain.project_info import ProjectInfo
    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor


class ProjectCatalog(Protocol, metaclass=ABCMeta):
    """Persist and look up named projects."""

    @abstractmethod
    async def create(self, *, project: ProjectInfo) -> None:
        """Add one globally unique project name."""

    @abstractmethod
    async def get(self, *, name: str) -> ProjectInfo:
        """Find a project by its exact name."""

    @abstractmethod
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ProjectInfo]:
        """Page through projects by stable name."""
