"""Describe intended decision-table result selection."""

from enum import StrEnum, unique


@unique
class HitPolicy(StrEnum):
    """Describe intended decision-table result selection."""

    UNIQUE = "unique"
    FIRST = "first"
    COLLECT = "collect"
