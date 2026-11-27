"""Inspect exact definition revisions without mutating the model."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope


class DefinitionQueries(Protocol, metaclass=ABCMeta):
    """Look up a definition by name or ID in its workspace."""

    @abstractmethod
    async def get_definition(
        self,
        *,
        scope: ModelScope,
        name: str | None,
        definition_id: DefinitionId | None,
        revision: int | None,
    ) -> Definition:
        """Return the current revision when no exact revision is specified."""
