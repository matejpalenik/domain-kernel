"""Recorded result of a durable action."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class AuditOutcome(StrEnum):
    """Recorded result of a durable action."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"
