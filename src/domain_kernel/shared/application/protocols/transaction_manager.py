from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager


class TransactionManager(Protocol, metaclass=ABCMeta):
    """Complete one transaction over a clean, operation-local resource."""

    @abstractmethod
    def begin(self) -> AbstractAsyncContextManager[None]:
        """Open one transaction over the operation-local resource.

        A successful exit commits the transaction. A failure before commit rolls it back.

        Raises:
            RuntimeError: The resource already has an active transaction when entered.
        """
