"""Outcome of one acceptance predicate on a captured candidate."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class CheckOutcome(StrEnum):
    """Outcome of one acceptance predicate on a captured candidate."""

    PASS = "pass"  # noqa: S105 - Acceptance outcome wire value.
    FAIL = "fail"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    ERROR = "error"
