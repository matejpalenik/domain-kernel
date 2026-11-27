"""A binary relationship with distinct directional bounds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.validators.definition_parts_validation import (
    DefinitionPartsValidation,
)
from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation
from domain_kernel.shared.domain.value_objects.relation_type_ref import RelationTypeRef
from domain_kernel.shared.domain.value_objects.relationship_cardinality import (
    RelationshipCardinality,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class RelationshipDefinition:
    """A binary relationship with distinct directional bounds."""

    source_concept_id: DefinitionReference
    target_concept_id: DefinitionReference
    cardinality: RelationshipCardinality
    kind: Literal[DefinitionKind.RELATIONSHIP] = DefinitionKind.RELATIONSHIP
    relation_type: RelationTypeRef | None = None

    def __post_init__(self) -> None:
        """Keep direction and exact concept references explicit."""
        DefinitionPartsValidation.require_body_kind(
            kind=self.kind, expected=DefinitionKind.RELATIONSHIP
        )

        ShapeFieldValidation.require_definition_reference(
            value=self.source_concept_id, field="Relationship source"
        )
        ShapeFieldValidation.require_definition_reference(
            value=self.target_concept_id, field="Relationship target"
        )

        RuntimeTypeValidation.require_exact(
            value=self.cardinality, expected=RelationshipCardinality, field="Cardinality"
        )

        if self.relation_type is not None:
            RuntimeTypeValidation.require_exact(
                value=self.relation_type, expected=RelationTypeRef, field="Directed relation type"
            )
