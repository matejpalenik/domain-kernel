"""Kinds of connections in a descriptive process."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class FlowKind(StrEnum):
    """Declared role of a connection between two named parts."""

    NORMAL = "normal"
    CONDITIONAL = "conditional"
    DEFAULT = "default"
    EXCEPTION = "exception"
