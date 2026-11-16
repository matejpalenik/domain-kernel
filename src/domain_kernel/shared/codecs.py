"""Version-aware codec contracts for application boundaries."""

from abc import ABCMeta, abstractmethod
from typing import Protocol


class VersionedCodec[T](Protocol, metaclass=ABCMeta):
    """Encode and decode one domain type for an explicitly selected wire version."""

    @abstractmethod
    def encode(self, *, value: T, schema_version: int | str) -> bytes:
        """Encode a value using the requested wire schema version."""
        ...

    @abstractmethod
    def decode(self, *, data: bytes, schema_version: int | str) -> T:
        """Decode bytes using the requested wire schema version."""
        ...
