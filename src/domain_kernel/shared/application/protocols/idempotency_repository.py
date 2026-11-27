from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.shared.application.idempotency.invocation import Invocation
    from domain_kernel.shared.application.idempotency.lease import Lease
    from domain_kernel.shared.application.idempotency.operation_outcome import OperationOutcome


class IdempotencyRepository(Protocol, metaclass=ABCMeta):
    """Persist durable invocation identity and fence its state transitions."""

    @abstractmethod
    async def claim(self, *, invocation: Invocation, owner: str) -> Lease | OperationOutcome:
        """Claim an available invocation or replay its completed outcome.

        Args:
            invocation: Scoped operation and key with the exact request hash.
            owner: Identity of the worker attempting to claim the operation.

        Returns:
            The new lease if work can proceed, or the stored outcome on replay.

        Raises:
            IdempotencyConflictError: The key is already bound to a different request hash.
            OperationInProgressError: A worker still holds an unexpired lease for the request.
        """

    @abstractmethod
    async def complete(
        self, *, invocation: Invocation, lease: Lease, outcome: OperationOutcome
    ) -> None:
        """Store the outcome under the current, unexpired lease.

        Raises:
            StaleStateError: The supplied lease no longer grants commit authority.
        """

    @abstractmethod
    async def renew(self, *, invocation: Invocation, lease: Lease) -> Lease:
        """Extend the current lease and invalidate its previous snapshot.

        Raises:
            StaleStateError: The supplied lease has changed or expired.
        """

    @abstractmethod
    async def release(self, *, invocation: Invocation, lease: Lease) -> None:
        """Release commit authority while preserving the original request identity.

        Raises:
            StaleStateError: The supplied lease has changed or expired.
        """
