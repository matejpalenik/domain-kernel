"""Describe one named scalar result in a decision table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.enums.data_type import DataType
from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation
from domain_kernel.shared.domain.value_objects.decision_value import DECISION_SCALAR_TYPES
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference
    from domain_kernel.shared.domain.types.scalar_data_type import ScalarDataType


@dataclass(frozen=True, kw_only=True)
class DecisionOutput:
    """A named result and the scalar type expected in each table rule."""

    id: str
    name: str
    definition_id: DefinitionReference
    data_type: ScalarDataType

    def __post_init__(self) -> None:
        """Require an exact scalar output and its authored meaning."""
        TextValidation.require_text(value=self.id, field="Decision output key")
        TextValidation.require_text(value=self.name, field="Decision output name")

        ShapeFieldValidation.require_definition_reference(
            value=self.definition_id, field="Decision output definition"
        )

        RuntimeTypeValidation.require_exact(
            value=self.data_type, expected=DataType, field="Decision output type"
        )
        if self.data_type not in DECISION_SCALAR_TYPES.values():
            raise ValueError("Decision outputs use scalar literals")
