"""Review disposition of one source occurrence."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class SourceDisposition(StrEnum):
    """Review disposition of one source occurrence."""

    MAPPED = "mapped"
    EXCLUDED = "excluded"
    UNRESOLVED = "unresolved"
    STALE = "stale"
