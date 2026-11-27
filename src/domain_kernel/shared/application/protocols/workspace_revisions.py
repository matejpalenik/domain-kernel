from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope


class WorkspaceRevisions(Protocol, metaclass=ABCMeta):
    """Read and advance the optimistic concurrency guard for a model."""

    @abstractmethod
    async def revision(self, *, scope: ModelScope) -> int:
        """Load the current revision for the exact model scope."""

    @abstractmethod
    async def advance(self, *, scope: ModelScope, expected_revision: int) -> None:
        """Advance exactly once if the current revision matches."""
