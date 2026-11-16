from __future__ import annotations

from abc import ABC
from inspect import isabstract
from typing import override

import pytest

from domain_kernel.shared.codecs import VersionedCodec


class StringCodec(VersionedCodec[str]):
    """Small codec implementation used to exercise the versioned protocol."""

    @override
    def encode(self, *, value: str, schema_version: str | int) -> bytes:
        """Serialize the test value with its explicit version."""
        return f"{schema_version}:{value}".encode()

    @override
    def decode(self, *, data: bytes, schema_version: str | int) -> str:
        """Decode only when the requested version matches the payload."""
        encoded_version, value = data.decode().split(":", maxsplit=1)

        if encoded_version != str(schema_version):
            raise ValueError("Unsupported schema version")

        return value


def test_versioned_codec_requires_explicit_wire_version() -> None:
    codec: VersionedCodec[str] = StringCodec()
    payload = codec.encode(value="model", schema_version="1")

    assert codec.decode(data=payload, schema_version="1") == "model"
    with pytest.raises(ValueError, match="Unsupported schema version"):
        _ = codec.decode(data=payload, schema_version="2")


def test_explicit_codec_implementation_requires_both_methods() -> None:
    class UnderspecifiedCodec(VersionedCodec[str], ABC):
        """A codec with neither versioned operation implemented."""

    assert isabstract(UnderspecifiedCodec)
