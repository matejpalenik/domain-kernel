"""Reference to a business concept."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class ConceptReferenceType:
    """Reference to a business concept."""

    concept: DefinitionReference
    kind: Literal["concept_reference"] = "concept_reference"

    def __post_init__(self) -> None:
        """Preserve the exact typed concept reference."""
        ShapeFieldValidation.require_attribute_type_kind(
            kind=self.kind, expected="concept_reference"
        )

        ShapeFieldValidation.require_definition_reference(value=self.concept, field="Concept")
