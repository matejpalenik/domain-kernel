"""An exact model definition or owner-qualified attribute in the semantic mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.enums.ontology_entity_kind import OntologyEntityKind
from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class ModelTermReference:
    """An exact model definition or owner-qualified attribute in the semantic mapping."""

    definition: DefinitionReference
    entity_kind: OntologyEntityKind
    local_path: Sequence[str] = ()

    def __post_init__(self) -> None:
        """Require a typed definition reference and an explicit attribute path."""
        ShapeFieldValidation.require_definition_reference(
            value=self.definition, field="Semantic definition"
        )
        RuntimeTypeValidation.require_exact(
            value=self.entity_kind, expected=OntologyEntityKind, field="Semantic kind"
        )
        path = SequenceValidation.snapshot_sequence(
            items=self.local_path, item_type=str, field="Semantic field path"
        )
        match path:
            case ():
                pass
            case ("attributes", identity):
                TextValidation.require_text(value=identity, field="Semantic attribute ID")
            case _:
                raise ValueError("Select an entire definition or an attribute by its stable ID")
        object.__setattr__(self, "local_path", path)
