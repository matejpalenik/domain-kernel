"""Describe a decision-table input and the model definition it uses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.data_shapes import require_definition_reference
from domain_kernel.shared.domain.model_values import DataType
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.shared.contracts import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class DecisionInput:
    """A symbolic input backed by a model definition."""

    id: str
    name: str
    definition_id: DefinitionReference
    data_type: DataType

    def __post_init__(self) -> None:
        """Retain the exact input symbol, label, model edge and type."""
        TextValidation.require_text(value=self.id, field="Decision input key")
        TextValidation.require_text(value=self.name, field="Decision input name")
        require_definition_reference(value=self.definition_id, field="Decision input definition")
        RuntimeTypeValidation.require_exact(
            value=self.data_type, expected=DataType, field="Decision input type"
        )
