"""Preserve an authored criterion that requires human judgement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, kw_only=True)
class ManualCriterion:
    """Preserve an authored criterion that requires human judgement."""

    kind: Literal["manual_criterion"] = "manual_criterion"

    def __post_init__(self) -> None:
        """Check the closed manual predicate discriminator."""
        if self.kind != "manual_criterion":
            raise ValueError("Use the manual criterion predicate kind")
