"""Version-aware codec contracts for application boundaries."""

from typing import Protocol


class VersionedCodec[T](Protocol):
    """Encode and decode one domain type for an explicitly selected wire version."""

    def encode(self, *, value: T, schema_version: int | str) -> bytes:
        """Encode a value using the requested wire schema version."""
        ...

    def decode(self, *, data: bytes, schema_version: int | str) -> T:
        """Decode bytes using the requested wire schema version."""
        ...
