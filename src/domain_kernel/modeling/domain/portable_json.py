"""Bounded strict JSON input shared by independently loadable SDK formats."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING

from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import is_non_string_sequence, require_exact

if TYPE_CHECKING:
    from domain_kernel.shared.hashing import JsonValue


class PortableReadError(ValueError):
    """A payload cannot be decoded within the portable input contract."""

    issue: Issue

    def __init__(self, *, code: str, message: str) -> None:
        """Expose a short diagnostic without storing the supplied payload."""
        self.issue = Issue(code=code, path=(), message=message)
        super().__init__(message)


def _object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    values = dict(pairs)
    if len(values) != len(pairs):
        raise ValueError("Duplicate JSON fields")
    return values


def _invalid_number(_value: str) -> None:
    raise ValueError("Use the declared scalar lexical representation")


_MAX_DEPTH = 64


def _bounded_depth(*, document: JsonValue, resource: str) -> None:
    stack = [(document, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > _MAX_DEPTH:
            raise PortableReadError(
                code=f"{resource}_depth", message="Use a bundle with at most 64 nested levels."
            )
        if isinstance(item, dict):
            stack.extend((part, depth + 1) for part in item.values())
        elif isinstance(item, Sequence) and is_non_string_sequence(item):
            stack.extend((part, depth + 1) for part in item)


def _input_bytes(*, payload: bytes | str, max_bytes: int, resource: str) -> bytes:
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("Set a positive integer byte limit")
    if type(payload) is str:
        if len(payload) > max_bytes:
            raise PortableReadError(
                code=f"{resource}_size", message="Use a bundle within the configured byte limit."
            )
        try:
            payload = payload.encode("utf-8")
        except UnicodeError:
            raise PortableReadError(
                code=f"{resource}_encoding", message="Use strictly valid UTF-8."
            ) from None
    if type(payload) is not bytes:
        raise TypeError("Supply the bundle as bytes or text")
    if len(payload) > max_bytes:
        raise PortableReadError(
            code=f"{resource}_size", message="Use a bundle within the configured byte limit."
        )
    return payload


def read_portable_object(
    *,
    payload: bytes | str,
    expected_hash: ContentHash | None,
    max_bytes: int,
    resource: str,
) -> dict[str, JsonValue]:
    """Check the exact received bytes before decoding one closed JSON object."""
    content = _input_bytes(payload=payload, max_bytes=max_bytes, resource=resource)
    if expected_hash is not None:
        require_exact(value=expected_hash, expected=ContentHash, field="Transport hash")
        if hash_bytes(content=content) != expected_hash:
            raise PortableReadError(
                code="transport_hash", message="Retrieve the exact expected bytes."
            )
    try:
        # The stdlib decoder returns only validated JSON scalars, arrays and string-keyed objects.
        raw: JsonValue = json.loads(  # pyright: ignore[reportAny]
            content.decode("utf-8"),
            object_pairs_hook=_object,
            parse_float=_invalid_number,
            parse_constant=_invalid_number,
        )
    except (ValueError, RecursionError):
        raise PortableReadError(
            code=f"{resource}_json", message="Supply strict UTF-8 JSON with unique fields."
        ) from None
    _bounded_depth(document=raw, resource=resource)
    if not isinstance(raw, dict):
        raise PortableReadError(code=f"{resource}_format", message="Supply a portable JSON object.")
    return raw
