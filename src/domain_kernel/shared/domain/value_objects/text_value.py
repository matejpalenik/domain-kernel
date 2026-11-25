"""Validate shared nonblank text values."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.validators.text_validation import TextValidation


@dataclass(frozen=True, kw_only=True)
class TextValue:
    """Base for domain text values that preserve internal whitespace."""

    value: str

    def __post_init__(self) -> None:
        """Preserve exact nonblank text, including internal whitespace."""
        field = type(self).__name__
        TextValidation.require_text(value=self.value, field=field)
        if self.value != self.value.strip():
            message = f"{field} cannot contain surrounding whitespace"
            raise ValueError(message)
