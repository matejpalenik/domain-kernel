"""Whether a constraint describes the model or its instances."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class ConstraintTarget(StrEnum):
    """Whether a constraint describes the model or its instances."""

    MODEL = "model"
    INSTANCE = "instance"
