"""One explicit asserted predicate awaiting or carrying review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.enums.ontology_entity_kind import OntologyEntityKind
from domain_kernel.shared.domain.enums.semantic_relation import SemanticRelation
from domain_kernel.shared.domain.value_objects.model_term_reference import ModelTermReference
from domain_kernel.shared.domain.value_objects.ontology_term_reference import OntologyTermReference
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.semantic_term import SemanticTerm

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
