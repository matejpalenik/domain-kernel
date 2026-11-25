"""The outcome of optional formal processing."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class SemanticStatus(StrEnum):
    """The outcome of optional formal processing."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    FAILED = "failed"
