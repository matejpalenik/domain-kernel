"""Encode JSON values in the SDK's canonical UTF-8 representation."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, final

from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from domain_kernel.shared.json_value import JsonValue


@final
class CanonicalJson:
    """Normalize and encode JSON for reproducible SDK records and payloads."""

    @staticmethod
    def encode(*, value: JsonValue) -> bytes:
        """Serialize a JSON value with stable key order and compact UTF-8 encoding."""
        encoded = json.dumps(
            CanonicalJson._normalize_json_value(value=value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )

        return encoded.encode("utf-8")

    @staticmethod
    def _normalize_json_value(*, value: JsonValue) -> JsonValue:
        """Snapshot supported JSON values without changing scalar types or array order."""
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
                normalized[key] = CanonicalJson._normalize_json_value(value=item)

            return normalized

        if isinstance(value, Sequence) and SequenceValidation.is_non_string_sequence(value=value):
            return [CanonicalJson._normalize_json_value(value=item) for item in value]

        raise TypeError("Value is outside the supported JSON subset")
