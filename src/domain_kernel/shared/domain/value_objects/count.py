from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Count:
    """Nonnegative exact integer value used for bounded counts."""

    value: int

    def __post_init__(self) -> None:
        """Reject booleans, non-integers, and negative counts."""
        if type(self.value) is not int:
            raise TypeError("Count value must be an exact integer")
        if self.value < 0:
            raise ValueError("Count value must be nonnegative")
