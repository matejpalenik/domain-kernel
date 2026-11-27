"""Select a final definition revision produced by the same review plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation


@dataclass(frozen=True, kw_only=True)
class MapToPlannedDefinition:
    """Select a final definition revision produced by the same review plan."""

    definition_id: DefinitionId
    reason: str
    kind: Literal["map_to_planned_definition"] = "map_to_planned_definition"

    def __post_init__(self) -> None:
        """Retain an exact planned identity and explicit rationale."""
        RuntimeTypeValidation.require_exact(
            value=self.definition_id, expected=DefinitionId, field="Planned definition"
        )
        TextValidation.require_text(value=self.reason, field="Mapping reason")

        RuntimeTypeValidation.require_exact(value=self.kind, expected=str, field="Plan action kind")
        if self.kind != "map_to_planned_definition":
            raise ValueError("Use the planned definition mapping action")
