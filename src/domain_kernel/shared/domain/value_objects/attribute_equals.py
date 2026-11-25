"""A trigger whose state is represented by one scalar attribute value."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class AttributeEquals:
    """A trigger whose state is represented by one scalar attribute value."""

    attribute: AttributeId
    value: str | int | bool

    def __post_init__(self) -> None:
        """Require a stable modeled attribute and a supported native value."""
        RuntimeTypeValidation.require_exact(
            value=self.attribute, expected=AttributeId, field="Rule attribute"
        )
        if type(self.value) not in (str, int, bool):
            raise TypeError("Use a string, integer or Boolean trigger value.")
