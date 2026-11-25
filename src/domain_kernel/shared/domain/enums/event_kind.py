"""Kinds of events in a descriptive process."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class EventKind(StrEnum):
    """Role of an event in the described process."""

    START = "start"
    END = "end"
    INTERMEDIATE = "intermediate"
    EXCEPTION = "exception"
