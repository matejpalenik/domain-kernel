"""Bind magnitude and unit attributes for one structured value."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.shared.domain.value_objects.ontology_term_reference import (
    OntologyTermReference,
    require_unit_term,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class QuantityBinding:
    """Bind magnitude and unit attributes for one structured value."""

    magnitude: AttributeId
    unit: AttributeId
    quantity_kind: OntologyTermReference | None = None

    def __post_init__(self) -> None:
        """Require distinct field IDs and validate any supplied term kind."""
        RuntimeTypeValidation.require_exact(
            value=self.magnitude, expected=AttributeId, field="Quantity magnitude"
        )
        RuntimeTypeValidation.require_exact(
            value=self.unit, expected=AttributeId, field="Quantity unit"
        )
        if self.magnitude == self.unit:
            raise ValueError("Quantity magnitude and unit must use distinct attributes")
        if self.quantity_kind is not None:
            require_unit_term(term=self.quantity_kind)
