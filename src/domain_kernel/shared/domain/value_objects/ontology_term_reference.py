"""Exact declared term and kind in one pinned document graph."""

from dataclasses import dataclass

from domain_kernel.shared.domain.enums.ontology_entity_kind import OntologyEntityKind
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class OntologyTermReference:
    """Exact declared term and kind in one pinned document graph."""

    source: OntologyDocumentPin
    term_iri: Iri
    entity_kind: OntologyEntityKind

    def __post_init__(self) -> None:
        """Preserve typed provenance without claiming the term has been materialized."""
        RuntimeTypeValidation.require_exact(
            value=self.source, expected=OntologyDocumentPin, field="Ontology source"
        )
        RuntimeTypeValidation.require_exact(
            value=self.term_iri, expected=Iri, field="Ontology term IRI"
        )
        RuntimeTypeValidation.require_exact(
            value=self.entity_kind, expected=OntologyEntityKind, field="Ontology kind"
        )


def require_unit_term(*, term: OntologyTermReference) -> None:
    """Require a declared individual or SKOS concept for a unit or quantity kind."""
    RuntimeTypeValidation.require_exact(
        value=term, expected=OntologyTermReference, field="Unit or quantity term"
    )
    if term.entity_kind not in (OntologyEntityKind.INDIVIDUAL, OntologyEntityKind.SKOS_CONCEPT):
        raise ValueError("Unit and quantity terms must be individuals or SKOS concepts")
