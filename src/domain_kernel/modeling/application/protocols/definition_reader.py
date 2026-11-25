"""Read one exact definition revision from workspace persistence."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.shared.contracts import ModelScope
    from domain_kernel.shared.domain.definitions import Definition


class DefinitionReader(Protocol, metaclass=ABCMeta):
    """Read detached definitions using the caller's transaction."""

    @abstractmethod
    async def get(
        self,
        *,
        scope: ModelScope,
        name: str | None,
        definition_id: DefinitionId | None,
        revision: int | None,
    ) -> Definition:
        """Read by exact name or ID, at the current or specified revision."""
