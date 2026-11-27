from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable

    from domain_kernel.shared.application.requests.artifact_write_request import (
        ArtifactWriteRequest,
    )
    from domain_kernel.shared.domain.entities.artifact import Artifact


@runtime_checkable
class ArtifactStore(Protocol, metaclass=ABCMeta):
    """Store immutable bytes plus metadata under an approved project-scoped key."""

    @abstractmethod
    def put(self, *, request: ArtifactWriteRequest, chunks: Iterable[bytes]) -> Artifact:
        """Write or exactly reuse one artifact at the approved destination.

        Args:
            request: Destination, expected digest and metadata for the write.
            chunks: Payload bytes in stream order.

        Returns:
            The stored artifact descriptor with the provider version when available.
        """

    @abstractmethod
    def get(self, *, artifact: Artifact, max_bytes: int) -> bytes:
        """Read and verify the exact bytes identified by the artifact.

        Args:
            artifact: Expected destination, digest and provider version when available.
            max_bytes: Maximum number of payload bytes to return.
        """

    @abstractmethod
    def verify(self, *, artifact: Artifact) -> bool:
        """Verify the exact bytes and artifact metadata."""
