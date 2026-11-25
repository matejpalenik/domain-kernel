"""Case-sensitive identity for a member of a business vocabulary."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.text_value import TextValue


@dataclass(frozen=True, kw_only=True)
class BusinessCode(TextValue):
    """Case-sensitive identity for a member of a business vocabulary."""
