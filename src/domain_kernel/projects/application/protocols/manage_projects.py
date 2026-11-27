from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.projects.application.commands.create_project import CreateProject
    from domain_kernel.projects.domain.project_info import ProjectInfo
    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor


class ManageProjects(Protocol, metaclass=ABCMeta):
    """Create, look up and page through projects."""

    @abstractmethod
    async def create(self, *, command: CreateProject) -> ProjectInfo:
        """Create the workspace and record its attribution atomically."""

    @abstractmethod
    async def get(self, *, name: str) -> ProjectInfo:
        """Look up a workspace by its exact name."""

    @abstractmethod
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ProjectInfo]:
        """Page through workspaces by stable name."""
