"""The question put to the selected reasoner."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class ReasoningTask(StrEnum):
    """The question put to the selected reasoner."""

    CONSISTENCY = "consistency"
    CLASSIFICATION = "classification"
    ENTAILMENT = "entailment"
