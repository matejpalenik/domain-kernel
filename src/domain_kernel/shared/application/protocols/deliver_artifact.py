from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from domain_kernel.shared.application.commands.deliver_artifact_command import (
        DeliverArtifactCommand,
    )
    from domain_kernel.shared.application.protocols.artifact_writer import ArtifactWriter
    from domain_kernel.shared.application.results.delivery_receipt import DeliveryReceipt
    from domain_kernel.shared.domain.entities.artifact import Artifact


class DeliverArtifact(Protocol, metaclass=ABCMeta):
    """Deliver or recover one artifact under a durable request identity."""

    @abstractmethod
    async def deliver(
        self,
        *,
        request: DeliverArtifactCommand,
        write: ArtifactWriter,
        verify: Callable[[Artifact], Awaitable[bool]],
    ) -> DeliveryReceipt:
        """Deliver the exact artifact or verify a receipt from a previous attempt.

        Args:
            request: The delivery intent and its scope, destination and attribution.
            write: Write or recover the artifact outside the database transaction.
            verify: Check the exact stored artifact, using the provider version when present.

        Returns:
            The verified artifact and the time its successful delivery was recorded.

        Raises:
            ArtifactConflictError: The returned artifact differs or verification returns false.
            StaleStateError: A recorded receipt cannot be bound to this delivery.
        """
