"""Collection semantics for a business field."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class CollectionKind(StrEnum):
    """Collection semantics for a business field."""

    SINGLE = "single"
    SET = "set"
    LIST = "list"
