"""Maximum significant digits in a decimal value."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class DecimalPrecision:
    """Maximum significant digits in a decimal value."""

    value: int

    def __post_init__(self) -> None:
        """Require a positive exact integer."""
        RuntimeTypeValidation.require_exact(
            value=self.value, expected=int, field="DecimalPrecision value"
        )
        if self.value < 1:
            raise ValueError("DecimalPrecision value must be positive")
