"""How a definition's interpretation was established."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class EvidenceBasis(StrEnum):
    """How a definition's interpretation was established."""

    DOCUMENTED = "documented"
    DATA_INFERENCE = "data_inference"
    HYPOTHESIS = "hypothesis"
    STATEMENT = "statement"
