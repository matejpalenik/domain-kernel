"""Whether the review requires verified executable success."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class CheckRequirement(StrEnum):
    """Whether the review requires verified executable success."""

    REQUIRED = "required"
    ADVISORY = "advisory"
