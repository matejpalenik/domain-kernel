"""Deterministic JSON serialization and content hashing primitives."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence

from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

type JsonValue = bool | int | float | str | Sequence[JsonValue] | dict[str, JsonValue] | None


def canonical_json_bytes(*, value: JsonValue) -> bytes:
    """Serialize a JSON value with stable key order and compact UTF-8 encoding."""
    encoded = json.dumps(
        _normalize_json_value(value),
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


def _normalize_json_value(value: JsonValue) -> JsonValue:
    if value is None or type(value) is bool or type(value) is int or type(value) is str:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Canonical JSON numbers must be finite")
        return value
    if isinstance(value, dict):
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("Canonical JSON object keys must be exact strings")
            normalized[key] = _normalize_json_value(item)
        return normalized
    if isinstance(value, Sequence) and SequenceValidation.is_non_string_sequence(value=value):
        return [_normalize_json_value(item) for item in value]
    raise TypeError("Value is outside the supported JSON subset")
