"""Hash exact bytes and canonical JSON."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, final

from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.identifiers.content_hash import ContentHash

if TYPE_CHECKING:
    from domain_kernel.shared.json_value import JsonValue


@final
class Hashing:
    """Compute SHA-256 content hashes for bytes and canonical JSON."""

    @staticmethod
    def hash_bytes(*, content: bytes) -> ContentHash:
        """Return the prefixed SHA-256 digest of exact bytes."""
        if type(content) is not bytes:
            raise TypeError("Hash input must be exact bytes")
        return ContentHash(f"sha256:{hashlib.sha256(content).hexdigest()}")

    @staticmethod
    def hash_json(*, value: JsonValue) -> ContentHash:
        """Hash the canonical JSON representation of a typed JSON value."""
        return Hashing.hash_bytes(content=CanonicalJson.encode(value=value))
