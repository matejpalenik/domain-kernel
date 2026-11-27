from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.projection_metadata import ProjectionMetadata
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation


def _require_chunks(*, value: object) -> None:
    """Require an iterable of chunks in place of a single text or binary buffer."""
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
