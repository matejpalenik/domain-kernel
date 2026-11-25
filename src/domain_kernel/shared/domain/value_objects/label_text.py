"""Display text for authored terminology."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.text_value import TextValue


@dataclass(frozen=True, kw_only=True)
class LabelText(TextValue):
    """Display text for authored terminology."""
