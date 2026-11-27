"""Encode and restore exact, versioned SDK records."""

from __future__ import annotations

import json
from base64 import b64decode, b64encode
from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite
from typing import TYPE_CHECKING, TypeGuard, final

from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.domain.codecs.decimal_text import DecimalText
from domain_kernel.shared.domain.codecs.record_restoration import RecordRestoration
from domain_kernel.shared.domain.codecs.wire_record_name import WireRecordName
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from domain_kernel.shared.json_value import JsonValue

from domain_kernel.shared.domain.codecs.record_registry import (
    ENUM_TYPES,
    OMIT_EMPTY_GROUP_FIELDS,
    RECORD_TYPES,
)

_SCALAR_MARKERS = frozenset({"time", "date", "decimal", "float", "bytes"})


@final
class RecordCodec:
    """Encode canonical SDK records and restore their stored identities."""

    @staticmethod
    def to_value(
        *,
        value: object,
        root_type: type[object] | None = None,
        utc_times: bool = False,
    ) -> JsonValue:
        """Encode one supported authored value, retaining exact nested types.

        Args:
            value: A supported scalar, sequence or SDK record to encode.
            root_type: An additional record type permitted for the outer value only.
            utc_times: Whether to normalize aware datetimes to UTC throughout the value.

        Raises:
            TypeError: A value has a type the record format cannot encode.
            ValueError: A scalar has no supported canonical representation.
        """
        tag = WireRecordName.for_type(record=type(value))
        if isinstance(value, StrEnum) and ENUM_TYPES.get(tag) is type(value):
            return {"enum": tag, "value": value.value}

        if value is None or type(value) is str or type(value) is int or type(value) is bool:
            return value
        if type(value) is bytes:
            return {"bytes": b64encode(value).decode("ascii")}
        if isinstance(value, (date, Decimal, float)):
            return RecordCodec._scalar_record(value=value, utc_times=utc_times)

        if RecordCodec._is_record_sequence(value):
            return tuple(RecordCodec.to_value(value=item, utc_times=utc_times) for item in value)

        if is_dataclass(value) and (
            RECORD_TYPES.get(tag) is type(value) or root_type is type(value)
        ):
            attributes: dict[str, JsonValue] = {}
            for field in fields(value):
                # Reflection is limited to registered dataclass fields and checked recursively.
                item: object = getattr(value, field.name)  # pyright: ignore[reportAny]
                if field.name in OMIT_EMPTY_GROUP_FIELDS.get(tag, ()) and item in (None, ()):
                    continue
                attributes[field.name] = RecordCodec.to_value(value=item, utc_times=utc_times)

            return {"record": tag, "fields": attributes}

        message = f"Cannot persist an unsupported SDK record type: {tag}"
        raise TypeError(message)

    @staticmethod
    def encode(*, value: object, root_type: type[object] | None = None) -> bytes:
        """Encode the canonical versioned form used by durable modeling state."""
        return CanonicalJson.encode(
            value={"version": 1, "record": RecordCodec.to_value(value=value, root_type=root_type)}
        )

    @staticmethod
    def decode[T](
        *,
        content: bytes,
        expected: type[T],
        root_type: type[object] | None = None,
    ) -> T:
        """Restore an exact supported record from canonical bytes.

        Args:
            content: Versioned canonical bytes in the current format.
            expected: Type the restored value must match.
            root_type: Additional record type permitted at the outer level only.

        Raises:
            TypeError: A stored record has unsupported fields or field types.
            ValueError: The envelope, restored type or canonical bytes fail verification.
        """
        raw = RecordCodec._decode_json(content=content)
        if not isinstance(raw, dict) or raw.get("version") != 1 or "record" not in raw:
            raise ValueError("Stored data has an unsupported modeling record version")

        loaded = RecordCodec._restore(value=raw["record"], root_type=root_type)
        if (
            not isinstance(loaded, expected)
            or RecordCodec.encode(value=loaded, root_type=root_type) != content
        ):
            raise ValueError("Stored data does not match its canonical SDK record")

        return loaded

    @staticmethod
    def _temporal_value(*, value: date | datetime, utc_times: bool) -> JsonValue:
        """Encode a date or a timestamp, optionally normalizing aware timestamps to UTC."""
        if isinstance(value, datetime):
            instant = (
                value.astimezone(UTC) if utc_times and value.utcoffset() is not None else value
            )
            return {"time": instant.isoformat()}
        return {"date": value.isoformat()}

    @staticmethod
    def _scalar_record(*, value: date | Decimal | float, utc_times: bool) -> JsonValue:
        """Preserve the exact decimal, floating-point or temporal value under a type tag."""
        if isinstance(value, date):
            return RecordCodec._temporal_value(value=value, utc_times=utc_times)
        if isinstance(value, Decimal):
            return {"decimal": DecimalText.canonical_decimal_text(value=value)}
        if not isfinite(value):
            raise ValueError("Use finite stored scalars")

        return {"float": float.hex(value)}

    @staticmethod
    def _is_record_sequence(value: object, /) -> TypeGuard[Sequence[object]]:
        """Distinguish arrays from text and binary data during recursive encoding."""
        return SequenceValidation.is_non_string_sequence(value=value)

    @staticmethod
    def _restore(*, value: JsonValue, root_type: type[object] | None = None) -> object:
        """Restore nested values while allowing the caller-supplied type at the root only."""
        if isinstance(value, dict):
            return RecordCodec._restore_object(value=value, root_type=root_type)
        if isinstance(value, Sequence) and SequenceValidation.is_non_string_sequence(value=value):
            return tuple(RecordCodec._restore(value=item) for item in value)

        return value

    @staticmethod
    def _restore_scalar(*, value: dict[str, JsonValue]) -> object:
        """Decode one tagged scalar and reject malformed or noncanonical values."""
        if set(value) == {"bytes"} and isinstance(encoded := value["bytes"], str):
            decoded = b64decode(encoded, validate=True)
            if b64encode(decoded).decode("ascii") == encoded:
                return decoded

        if set(value) == {"time"} and isinstance(time := value["time"], str):
            return datetime.fromisoformat(time)
        if set(value) == {"date"} and isinstance(day := value["date"], str):
            return date.fromisoformat(day)
        if set(value) == {"decimal"} and isinstance(decimal := value["decimal"], str):
            return Decimal(decimal)

        if set(value) == {"float"} and isinstance(scalar := value["float"], str):
            number = float.fromhex(scalar)
            if isfinite(number) and number.hex() == scalar:
                return number

        raise ValueError("Stored data contains a malformed scalar")

    @staticmethod
    def _restore_object(
        *,
        value: dict[str, JsonValue],
        root_type: type[object] | None,
    ) -> object:
        """Restore a registered enum or record from its tag and exact encoded fields."""
        if set(value) == {"enum", "value"}:
            tag, scalar = value["enum"], value["value"]
            if isinstance(tag, str) and isinstance(scalar, str) and tag in ENUM_TYPES:
                return ENUM_TYPES[tag](scalar)
        elif _SCALAR_MARKERS.intersection(value):
            return RecordCodec._restore_scalar(value=value)
        elif set(value) == {"record", "fields"}:
            tag, attributes = value["record"], value["fields"]
            if isinstance(tag, str) and isinstance(attributes, dict):
                record = RECORD_TYPES.get(tag)
                if root_type is not None and WireRecordName.for_type(record=root_type) == tag:
                    record = root_type

                if record is not None:
                    return RecordRestoration.construct_record(
                        record=record,
                        attributes={
                            key: RecordCodec._restore(value=field)
                            for key, field in attributes.items()
                        },
                    )

        raise ValueError("Stored data contains an invalid SDK record")

    @staticmethod
    def _decode_json(*, content: bytes) -> JsonValue:
        """Decode persisted JSON into the primitive values accepted by the record reader."""
        # The standard JSON parser creates primitive values, arrays and string-keyed objects.
        return json.loads(content)  # pyright: ignore[reportAny]
