"""Directions of a descriptive process gateway."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class GatewayDirection(StrEnum):
    """A gateway either splits or joins its incident flows."""

    SPLIT = "split"
    JOIN = "join"
