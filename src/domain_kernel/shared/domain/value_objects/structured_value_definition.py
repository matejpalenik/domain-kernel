"""Reusable embedded fields and an optional quantity binding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.enums.data_type import DataType
from domain_kernel.shared.domain.validators.definition_parts_validation import (
    DefinitionPartsValidation,
)
from domain_kernel.shared.domain.value_objects.quantity_binding import QuantityBinding
from domain_kernel.shared.domain.value_objects.scalar_value_type import ScalarValueType
from domain_kernel.shared.domain.value_objects.value_set_type import ValueSetType
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition


@dataclass(frozen=True, kw_only=True)
class StructuredValueDefinition:
    """Reusable embedded fields and an optional quantity binding."""

    attributes: Sequence[AttributeDefinition]
    quantity: QuantityBinding | None = None
    kind: Literal[DefinitionKind.STRUCTURED_VALUE] = DefinitionKind.STRUCTURED_VALUE

    def __post_init__(self) -> None:
        """Validate the declared local shape of an embeddable value."""
        DefinitionPartsValidation.require_body_kind(
            kind=self.kind, expected=DefinitionKind.STRUCTURED_VALUE
        )
        attributes = DefinitionPartsValidation.snapshot_attributes(attributes=self.attributes)
        if not attributes:
            raise ValueError("A structured value needs at least one field")
        if self.quantity is not None:
            RuntimeTypeValidation.require_exact(
                value=self.quantity, expected=QuantityBinding, field="Quantity binding"
            )
            _validate_quantity_fields(attributes=attributes, quantity=self.quantity)
        object.__setattr__(self, "attributes", attributes)


def _validate_quantity_fields(
    *, attributes: tuple[AttributeDefinition, ...], quantity: QuantityBinding
) -> None:
    by_id = {field.id: field for field in attributes}
    magnitude = by_id.get(quantity.magnitude)
    unit = by_id.get(quantity.unit)
    if magnitude is None or unit is None:
        raise ValueError("Quantity magnitude and unit must be fields on this structured value")
    if (
        not DefinitionPartsValidation.is_required_single(field=magnitude)
        or not isinstance(magnitude.value_type, ScalarValueType)
        or magnitude.value_type.data_type is not DataType.DECIMAL
    ):
        raise ValueError("Quantity magnitude must be a required, single-valued non-null decimal")
    if not DefinitionPartsValidation.is_required_single(field=unit) or not isinstance(
        unit.value_type, ValueSetType
    ):
        raise ValueError("Quantity unit must be a required, single-valued non-null value-set field")
