"""Whether the known business codes exhaust the permitted values."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class ValueSetMembership(StrEnum):
    """Whether the known business codes exhaust the permitted values."""

    CLOSED = "closed"
    OPEN = "open"
