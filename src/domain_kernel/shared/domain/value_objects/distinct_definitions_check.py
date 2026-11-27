"""Require two resolved identities to be distinct."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class DistinctDefinitionsCheck:
    """Require two resolved identities to be distinct."""

    left: DefinitionReference
    right: DefinitionReference
    kind: Literal["distinct_definitions"] = "distinct_definitions"

    def __post_init__(self) -> None:
        """Bind both exact references without resolving them."""
        ShapeFieldValidation.require_definition_reference(value=self.left, field="Left definition")
        ShapeFieldValidation.require_definition_reference(
            value=self.right, field="Right definition"
        )

        if self.kind != "distinct_definitions":
            raise ValueError("Use the distinct definitions predicate kind")
