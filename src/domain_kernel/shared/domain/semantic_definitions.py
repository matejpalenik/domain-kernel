"""Reviewed ontology modules and typed formal assertions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.data_shapes import require_definition_reference
from domain_kernel.shared.domain.ontology_assets import OntologyEntityKind, OntologyTermReference
from domain_kernel.shared.domain.ontology_closure import OntologyClosure
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference


@unique
class SemanticRelation(StrEnum):
    """Supported asserted predicates using their standard IRIs."""

    SUBCLASS_OF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
    SUBPROPERTY_OF = "http://www.w3.org/2000/01/rdf-schema#subPropertyOf"
    EQUIVALENT_CLASS = "http://www.w3.org/2002/07/owl#equivalentClass"
    EQUIVALENT_PROPERTY = "http://www.w3.org/2002/07/owl#equivalentProperty"
    DISJOINT_WITH = "http://www.w3.org/2002/07/owl#disjointWith"
    INVERSE_OF = "http://www.w3.org/2002/07/owl#inverseOf"
    SAME_AS = "http://www.w3.org/2002/07/owl#sameAs"
    DIFFERENT_FROM = "http://www.w3.org/2002/07/owl#differentFrom"
    EXACT_MATCH = "http://www.w3.org/2004/02/skos/core#exactMatch"
    CLOSE_MATCH = "http://www.w3.org/2004/02/skos/core#closeMatch"
    BROAD_MATCH = "http://www.w3.org/2004/02/skos/core#broadMatch"
    NARROW_MATCH = "http://www.w3.org/2004/02/skos/core#narrowMatch"
    RELATED_MATCH = "http://www.w3.org/2004/02/skos/core#relatedMatch"
    SEE_ALSO = "http://www.w3.org/2000/01/rdf-schema#seeAlso"
    IS_DEFINED_BY = "http://www.w3.org/2000/01/rdf-schema#isDefinedBy"


@dataclass(frozen=True, kw_only=True)
class ModelTermReference:
    """An exact model definition or owner-qualified attribute in the semantic mapping."""

    definition: DefinitionReference
    entity_kind: OntologyEntityKind
    local_path: Sequence[str] = ()

    def __post_init__(self) -> None:
        """Require a typed definition reference and an explicit attribute path."""
        require_definition_reference(value=self.definition, field="Semantic definition")
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


type SemanticTerm = ModelTermReference | OntologyTermReference

_EXPECTED = {
    SemanticRelation.SUBCLASS_OF: OntologyEntityKind.CLASS,
    SemanticRelation.EQUIVALENT_CLASS: OntologyEntityKind.CLASS,
    SemanticRelation.DISJOINT_WITH: OntologyEntityKind.CLASS,
    SemanticRelation.INVERSE_OF: OntologyEntityKind.OBJECT_PROPERTY,
    SemanticRelation.SAME_AS: OntologyEntityKind.INDIVIDUAL,
    SemanticRelation.DIFFERENT_FROM: OntologyEntityKind.INDIVIDUAL,
    SemanticRelation.EXACT_MATCH: OntologyEntityKind.SKOS_CONCEPT,
    SemanticRelation.CLOSE_MATCH: OntologyEntityKind.SKOS_CONCEPT,
    SemanticRelation.BROAD_MATCH: OntologyEntityKind.SKOS_CONCEPT,
    SemanticRelation.NARROW_MATCH: OntologyEntityKind.SKOS_CONCEPT,
    SemanticRelation.RELATED_MATCH: OntologyEntityKind.SKOS_CONCEPT,
}
_PROPERTIES = frozenset(
    {
        OntologyEntityKind.OBJECT_PROPERTY,
        OntologyEntityKind.DATA_PROPERTY,
        OntologyEntityKind.ANNOTATION_PROPERTY,
        OntologyEntityKind.RDF_PROPERTY,
    }
)


@dataclass(frozen=True, kw_only=True)
class SemanticLinkDefinition:
    """One explicit asserted predicate awaiting or carrying review."""

    subject: SemanticTerm
    relation: SemanticRelation
    object: SemanticTerm
    kind: Literal[DefinitionKind.SEMANTIC_LINK] = DefinitionKind.SEMANTIC_LINK

    def __post_init__(self) -> None:
        """Verify identical typed endpoints for predicates with a closed domain."""
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=DefinitionKind, field="Definition kind"
        )
        if self.kind is not DefinitionKind.SEMANTIC_LINK:
            raise ValueError("Select the semantic-link body kind")
        RuntimeTypeValidation.require_exact(
            value=self.relation, expected=SemanticRelation, field="Semantic predicate"
        )
        if type(self.subject) not in (ModelTermReference, OntologyTermReference) or type(
            self.object
        ) not in (ModelTermReference, OntologyTermReference):
            raise TypeError("Select exact typed semantic endpoints")
        subject, target = self.subject.entity_kind, self.object.entity_kind
        required = _EXPECTED.get(self.relation)
        if required is not None and (subject is not required or target is not required):
            message = f"Select {required.value} endpoints for this semantic relation"
            raise ValueError(message)
        if self.relation in (
            SemanticRelation.SUBPROPERTY_OF,
            SemanticRelation.EQUIVALENT_PROPERTY,
        ) and (
            subject not in _PROPERTIES
            or target not in _PROPERTIES
            or (subject is not target and OntologyEntityKind.RDF_PROPERTY not in (subject, target))
        ):
            raise ValueError("Select compatible asserted property kinds")


@dataclass(frozen=True, kw_only=True)
class OntologyModuleDefinition:
    """Explicit adoption of a complete immutable ontology module."""

    ontology: OntologyClosure
    kind: Literal[DefinitionKind.ONTOLOGY_MODULE] = DefinitionKind.ONTOLOGY_MODULE

    def __post_init__(self) -> None:
        """Require the verified original ontology closure."""
        RuntimeTypeValidation.require_exact(
            value=self.ontology, expected=OntologyClosure, field="Adopted ontology"
        )
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=DefinitionKind, field="Definition kind"
        )
        if self.kind is not DefinitionKind.ONTOLOGY_MODULE:
            raise ValueError("Select the ontology-module body kind")
