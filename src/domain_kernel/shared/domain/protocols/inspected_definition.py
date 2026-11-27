"""Read the identity and revision captured for an activity reference."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope


@runtime_checkable
class InspectedDefinition(Protocol, metaclass=ABCMeta):
    """Identity and revision exposed by an inspected model-definition record."""

    @property
    @abstractmethod
    def id(self) -> DefinitionId:
        """The stable identity of the inspected definition."""

    @property
    @abstractmethod
    def scope(self) -> ModelScope:
        """The workspace that owns the definition."""

    @property
    @abstractmethod
    def revision(self) -> int:
        """The exact revision captured by the reference."""
