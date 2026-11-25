"""Exact optional limits on significant and fractional digits."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain_kernel.shared.domain.value_objects.decimal_precision import DecimalPrecision
from domain_kernel.shared.domain.value_objects.decimal_scale import DecimalScale
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class DecimalFacets:
    """Exact optional limits on significant and fractional digits."""

    precision: DecimalPrecision | None = None
    scale: DecimalScale | None = None

    def __post_init__(self) -> None:
        """Validate optional limits without supplying implicit defaults."""
        if self.precision is None and self.scale is None:
            raise ValueError("DecimalFacets requires at least one limit")
        if self.precision is not None:
            RuntimeTypeValidation.require_exact(
                value=self.precision, expected=DecimalPrecision, field="Decimal precision"
            )
        if self.scale is not None:
            RuntimeTypeValidation.require_exact(
                value=self.scale, expected=DecimalScale, field="Decimal scale"
            )
            if self.precision is not None and self.scale.value > self.precision.value:
                raise ValueError("Decimal scale cannot exceed precision")


def validate_decimal_value(*, value: Decimal, facets: DecimalFacets) -> None:
    """Check an exact finite decimal against its declared facets."""
    RuntimeTypeValidation.require_exact(value=value, expected=Decimal, field="Decimal value")
    RuntimeTypeValidation.require_exact(
        value=facets, expected=DecimalFacets, field="Decimal facets"
    )
    if not value.is_finite():
        raise ValueError("Decimal value must be finite")
    _, digits, stored_exponent = value.as_tuple()
    exponent = int(stored_exponent)
    significant = len(digits)
    if value.is_zero():
        significant, exponent = 1, 0
    else:
        # Remove trailing zeros by adjusting the exact exponent without Context rounding.
        while digits[significant - 1] == 0:
            significant -= 1
            exponent += 1
    if facets.precision is not None and significant > facets.precision.value:
        raise ValueError("Decimal value exceeds precision")
    if facets.scale is not None and -exponent > facets.scale.value:
        raise ValueError("Decimal value exceeds scale")
