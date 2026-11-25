"""Represent an exact finite number without exponent, trailing zeros or signed zero."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal


def canonical_decimal_text(*, value: Decimal) -> str:
    """Represent an exact finite number without exponent, trailing zeros or signed zero."""
    if not value.is_finite():
        raise ValueError("Use a finite decimal")
    if not value:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
