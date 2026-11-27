"""Independent bounds for one direction of a relationship."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.count import Count
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

_ZERO = Count(value=0)


_ONE = Count(value=1)


@dataclass(frozen=True, kw_only=True)
class CardinalityBounds:
    """Independent bounds for one direction of a relationship."""

    minimum: Count = _ZERO
    maximum: Count | None = _ONE

    def __post_init__(self) -> None:
        """Keep finite participation bounds in ascending order."""
        RuntimeTypeValidation.require_exact(
            value=self.minimum, expected=Count, field="Cardinality minimum"
        )
        if self.maximum is not None:
            RuntimeTypeValidation.require_exact(
                value=self.maximum, expected=Count, field="Cardinality maximum"
            )
            if self.minimum.value > self.maximum.value:
                raise ValueError("Cardinality maximum must be at least the minimum")
