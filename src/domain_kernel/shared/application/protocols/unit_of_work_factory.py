from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager


from domain_kernel.shared.application.protocols.transaction import Transaction


class UnitOfWorkFactory[T: Transaction](Protocol, metaclass=ABCMeta):
    """Acquire the collaborators for one operation without starting its transaction."""

    @abstractmethod
    def __call__(self) -> AbstractAsyncContextManager[T]:
        """Return a context that releases the acquired resources on every exit."""
