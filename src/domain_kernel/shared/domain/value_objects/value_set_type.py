"""Reference to a vocabulary of business codes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class ValueSetType:
    """Reference to a vocabulary of business codes."""

    value_set: DefinitionReference
    kind: Literal["value_set"] = "value_set"

    def __post_init__(self) -> None:
        """Preserve the exact typed vocabulary reference."""
        ShapeFieldValidation.require_attribute_type_kind(kind=self.kind, expected="value_set")

        ShapeFieldValidation.require_definition_reference(value=self.value_set, field="Value set")
