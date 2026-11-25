"""Require a valid quantity and unit vocabulary on one structured value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation

if TYPE_CHECKING:
    from domain_kernel.shared.contracts import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class QuantityRequiredCheck:
    """Require a valid quantity and unit vocabulary on one structured value."""

    structure: DefinitionReference
    kind: Literal["quantity_required"] = "quantity_required"

    def __post_init__(self) -> None:
        """Bind the exact structured value reference."""
        ShapeFieldValidation.require_definition_reference(
            value=self.structure, field="Structured value"
        )
        if self.kind != "quantity_required":
            raise ValueError("Use the quantity required predicate kind")
