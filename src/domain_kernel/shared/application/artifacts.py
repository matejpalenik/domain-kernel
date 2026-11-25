"""Storage port and exact typed delivery metadata."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.value_objects.projection_metadata import ProjectionMetadata
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.identifiers.model_id import ModelId
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId


@dataclass(frozen=True, kw_only=True)
class ArtifactWrite(ProjectionMetadata):
    """Request an immutable scoped destination for an exact payload."""

    project_id: ProjectId
    model_id: ModelId | None
    store: str
    key: str
    media_type: str
    expected_hash: ContentHash

    def __post_init__(self) -> None:
        """Validate the request using the same metadata rules as the resulting artifact."""
        ProjectionMetadata.__post_init__(self)
        _ = self.artifact()
        TextValidation.require_text(value=self.media_type, field="Artifact media type")

    def artifact(self, *, provider_version: str | None = None) -> Artifact:
        """Materialize the expected identity for a provider receipt."""
        return Artifact(
            project_id=self.project_id,
            model_id=self.model_id,
            store=self.store,
            key=self.key,
            content_hash=self.expected_hash,
            provider_version=provider_version,
            projection_limits=self.projection_limits,
            semantic=self.semantic,
            schema=self.schema,
            consumer_obligations=self.consumer_obligations,
        )


def _require_chunks(*, value: object) -> None:
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Iterable):
        raise TypeError("Supply an iterable of byte chunks")


@dataclass(frozen=True, kw_only=True)
class ExportPayload(ProjectionMetadata):
    """Portable bytes and delivery metadata produced from one exact publication."""

    media_type: str
    content_hash: ContentHash
    chunks: Iterable[bytes]

    def __post_init__(self) -> None:
        """Detach metadata and require an explicit byte stream and digest."""
        ProjectionMetadata.__post_init__(self)
        TextValidation.require_text(value=self.media_type, field="Export media type")
        RuntimeTypeValidation.require_exact(
            value=self.content_hash, expected=ContentHash, field="Export byte hash"
        )
        _require_chunks(value=self.chunks)


@runtime_checkable
class ArtifactStore(Protocol, metaclass=ABCMeta):
    """Store immutable bytes plus metadata under an approved project-scoped key."""

    @abstractmethod
    def put(self, *, request: ArtifactWrite, chunks: Iterable[bytes]) -> Artifact:
        """Write or exactly reuse one artifact."""

    @abstractmethod
    def get(self, *, artifact: Artifact, max_bytes: int) -> bytes:
        """Read bounded verified artifact bytes."""

    @abstractmethod
    def verify(self, *, artifact: Artifact) -> bool:
        """Verify the exact bytes and artifact metadata."""
