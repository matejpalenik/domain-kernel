"""Materialize a selected reference pack inside the owning workspace transaction."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel._shared.application.persistence import Transaction

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.contracts import ModelScope


class SelectedPacks(Protocol, metaclass=ABCMeta):
    """Store one explicitly selected immutable pack per workspace."""

    @abstractmethod
    async def attach(self, *, scope: ModelScope, pack: ReferencePack) -> None:
        """Attach the exact selection to a newly created model."""

    @abstractmethod
    async def get(self, *, scope: ModelScope) -> ReferencePack | None:
        """Return the stored pack snapshot without consulting the catalog."""

    @abstractmethod
    async def replace(
        self, *, scope: ModelScope, previous: ReferencePackPin | None, pack: ReferencePack | None
    ) -> None:
        """Change the exact selected snapshot inside the guarded review transaction."""


@runtime_checkable
class PackSelectionTransaction(Transaction, Protocol, metaclass=ABCMeta):
    """Expose pack persistence as an optional workspace capability."""

    @property
    @abstractmethod
    def packs(self) -> SelectedPacks:
        """Return the selected pack repository bound to this operation."""
