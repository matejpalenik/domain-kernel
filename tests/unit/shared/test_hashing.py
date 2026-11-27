from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.json_value import JsonValue


def test_canonical_json_uses_stable_key_order_and_compact_utf8() -> None:
    first: JsonValue = {"z": 1, "a": "café"}
    second: JsonValue = {"a": "café", "z": 1}

    assert CanonicalJson.encode(value=first) == b'{"a":"caf\xc3\xa9","z":1}'
    assert CanonicalJson.encode(value=first) == CanonicalJson.encode(value=second)


def test_canonical_json_preserves_scalar_types() -> None:
    assert CanonicalJson.encode(value={"value": 1}) != CanonicalJson.encode(value={"value": True})
    assert CanonicalJson.encode(value={"value": 1}) != CanonicalJson.encode(value={"value": 1.0})


def test_canonical_json_normalizes_nested_sequences_without_reordering() -> None:
    values = ["recruitment", "selection"]
    listed: JsonValue = {"scope": [values, ["safeguards"]]}
    frozen: JsonValue = {"scope": (("recruitment", "selection"), ("safeguards",))}
    expected = b'{"scope":[["recruitment","selection"],["safeguards"]]}'

    assert CanonicalJson.encode(value=listed) == expected
    assert CanonicalJson.encode(value=frozen) == expected
    assert Hashing.hash_json(value=listed) == Hashing.hash_json(value=frozen)
    assert values == ["recruitment", "selection"]


@pytest.mark.parametrize("buffer", [b"abc", bytearray(b"abc"), memoryview(b"abc")])
def test_canonical_json_rejects_nested_byte_buffers(buffer: Sequence[int]) -> None:
    with pytest.raises(TypeError, match="supported JSON subset"):
        _ = CanonicalJson.encode(value={"scope": [buffer]})


def test_canonical_json_rejects_non_finite_numbers() -> None:
    with pytest.raises(ValueError, match="finite"):
        _ = CanonicalJson.encode(value={"value": float("nan")})


def test_hash_bytes_uses_prefixed_sha256() -> None:
    digest = Hashing.hash_bytes(content=b"domain-kernel")

    expected = f"sha256:{hashlib.sha256(b'domain-kernel').hexdigest()}"

    assert digest.value == expected


def test_hash_json_is_independent_of_mapping_insertion_order() -> None:
    assert Hashing.hash_json(value={"a": 1, "b": 2}) == Hashing.hash_json(value={"b": 2, "a": 1})


def test_hash_json_returns_content_hash_value_object() -> None:
    assert Hashing.hash_json(value={"id": "machine"}).value.startswith("sha256:")
