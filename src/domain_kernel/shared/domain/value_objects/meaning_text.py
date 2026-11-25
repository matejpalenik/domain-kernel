"""Prose stating the meaning of an authored value."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.text_value import TextValue


@dataclass(frozen=True, kw_only=True)
class MeaningText(TextValue):
    """Prose stating the meaning of an authored value."""
