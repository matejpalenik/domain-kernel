"""Embed a reusable structured value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation

if TYPE_CHECKING:
    from domain_kernel.shared.contracts import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class StructuredValueType:
    """Embed a reusable structured value."""

    structure: DefinitionReference
    kind: Literal["structured_value"] = "structured_value"

    def __post_init__(self) -> None:
        """Preserve the exact typed embedding reference."""
        ShapeFieldValidation.require_attribute_type_kind(
            kind=self.kind, expected="structured_value"
        )
        ShapeFieldValidation.require_definition_reference(value=self.structure, field="Structure")
