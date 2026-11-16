"""Deterministic JSON serialization and content hashing primitives."""

from __future__ import annotations

import hashlib
import json
import math

from domain_kernel.shared.identifiers.content_hash import ContentHash

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None


def canonical_json_bytes(*, value: JsonValue) -> bytes:
    """Serialize a JSON value with stable key order and compact UTF-8 encoding."""
    _validate_json_value(value)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return encoded.encode("utf-8")


def hash_bytes(*, content: bytes) -> ContentHash:
    """Return the prefixed SHA-256 digest of exact bytes."""
    if type(content) is not bytes:
        raise TypeError("Hash input must be exact bytes")
    return ContentHash(f"sha256:{hashlib.sha256(content).hexdigest()}")


def hash_json(*, value: JsonValue) -> ContentHash:
    """Hash the canonical JSON representation of a typed JSON value."""
    return hash_bytes(content=canonical_json_bytes(value=value))


def _validate_json_value(value: JsonValue) -> None:
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Canonical JSON numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("Canonical JSON object keys must be exact strings")
            _validate_json_value(item)
        return
    raise TypeError("Value is outside the supported JSON subset")
