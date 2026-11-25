"""Effect of a change on the declared business contract."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class Compatibility(StrEnum):
    """Effect of a change on the declared business contract."""

    INITIAL = "initial"
    COMPATIBLE = "compatible"
    BREAKING = "breaking"
    UNDETERMINED = "undetermined"
