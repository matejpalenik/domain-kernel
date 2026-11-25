"""Maximum fractional digits in a decimal value."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class DecimalScale:
    """Maximum fractional digits in a decimal value."""

    value: int

    def __post_init__(self) -> None:
        """Require a nonnegative exact integer."""
        RuntimeTypeValidation.require_exact(
            value=self.value, expected=int, field="DecimalScale value"
        )
        if self.value < 0:
            raise ValueError("DecimalScale value must be nonnegative")
