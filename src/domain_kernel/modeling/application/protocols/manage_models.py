from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.modeling.application.commands.create_model import CreateModel
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor


class ManageModels(Protocol, metaclass=ABCMeta):
    """Create, look up and page through a project's models."""

    @abstractmethod
    async def create(self, *, command: CreateModel) -> ModelInfo:
        """Create the workspace and record its attribution atomically."""

    @abstractmethod
    async def get(self, *, name: str) -> ModelInfo:
        """Look up a workspace by its exact name."""

    @abstractmethod
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ModelInfo]:
        """Page through workspaces by stable name."""
