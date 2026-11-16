from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from domain_kernel.shared.hashing import JsonValue, canonical_json_bytes, hash_bytes, hash_json

if TYPE_CHECKING:
    from collections.abc import Sequence


def test_canonical_json_uses_stable_key_order_and_compact_utf8() -> None:
    first: JsonValue = {"z": 1, "a": "café"}
    second: JsonValue = {"a": "café", "z": 1}

    assert canonical_json_bytes(value=first) == b'{"a":"caf\xc3\xa9","z":1}'
    assert canonical_json_bytes(value=first) == canonical_json_bytes(value=second)


def test_canonical_json_preserves_scalar_types() -> None:
    assert canonical_json_bytes(value={"value": 1}) != canonical_json_bytes(value={"value": True})
    assert canonical_json_bytes(value={"value": 1}) != canonical_json_bytes(value={"value": 1.0})


def test_canonical_json_normalizes_nested_sequences_without_reordering() -> None:
    values = ["recruitment", "selection"]
    listed: JsonValue = {"scope": [values, ["safeguards"]]}
    frozen: JsonValue = {"scope": (("recruitment", "selection"), ("safeguards",))}
    expected = b'{"scope":[["recruitment","selection"],["safeguards"]]}'

    assert canonical_json_bytes(value=listed) == expected
    assert canonical_json_bytes(value=frozen) == expected
    assert hash_json(value=listed) == hash_json(value=frozen)
    assert values == ["recruitment", "selection"]


@pytest.mark.parametrize("buffer", [b"abc", bytearray(b"abc"), memoryview(b"abc")])
def test_canonical_json_rejects_nested_byte_buffers(buffer: Sequence[int]) -> None:
    with pytest.raises(TypeError, match="supported JSON subset"):
        _ = canonical_json_bytes(value={"scope": [buffer]})


def test_canonical_json_rejects_non_finite_numbers() -> None:
    with pytest.raises(ValueError, match="finite"):
        _ = canonical_json_bytes(value={"value": float("nan")})


def test_hash_bytes_uses_prefixed_sha256() -> None:
    digest = hash_bytes(content=b"domain-kernel")

    expected = f"sha256:{hashlib.sha256(b'domain-kernel').hexdigest()}"

    assert digest.value == expected


def test_hash_json_is_independent_of_mapping_insertion_order() -> None:
    assert hash_json(value={"a": 1, "b": 2}) == hash_json(value={"b": 2, "a": 1})


def test_hash_json_returns_content_hash_value_object() -> None:
    assert hash_json(value={"id": "machine"}).value.startswith("sha256:")
