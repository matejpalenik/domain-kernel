"""Inspect asserted declarations and imports only in the selected graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.shared.domain.enums.ontology_entity_kind import OntologyEntityKind
from domain_kernel.shared.domain.errors.invalid_ontology_error import InvalidOntologyError
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.ontology_term_reference import OntologyTermReference

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin
    from domain_kernel.shared.domain.value_objects.ontology_statement import OntologyStatement


_RDF_TYPE = Iri(value="http://www.w3.org/1999/02/22-rdf-syntax-ns#type")


_OWL = "http://www.w3.org/2002/07/owl#"


_OWL_ONTOLOGY = Iri(value=f"{_OWL}Ontology")


_OWL_VERSION = Iri(value=f"{_OWL}versionIRI")


_OWL_IMPORT = Iri(value=f"{_OWL}imports")


_KIND_BY_IRI = {
    f"{_OWL}Class": OntologyEntityKind.CLASS,
    "http://www.w3.org/2000/01/rdf-schema#Class": OntologyEntityKind.CLASS,
    f"{_OWL}ObjectProperty": OntologyEntityKind.OBJECT_PROPERTY,
    f"{_OWL}DatatypeProperty": OntologyEntityKind.DATA_PROPERTY,
    f"{_OWL}AnnotationProperty": OntologyEntityKind.ANNOTATION_PROPERTY,
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property": OntologyEntityKind.RDF_PROPERTY,
    "http://www.w3.org/2000/01/rdf-schema#Datatype": OntologyEntityKind.DATATYPE,
    f"{_OWL}NamedIndividual": OntologyEntityKind.INDIVIDUAL,
    "http://www.w3.org/2004/02/skos/core#Concept": OntologyEntityKind.SKOS_CONCEPT,
}


def declaration_inventory(
    *, pin: OntologyDocumentPin, statements: Sequence[OntologyStatement]
) -> tuple[tuple[OntologyTermReference, ...], tuple[Iri, ...]]:
    """Inspect asserted declarations and imports only in the selected graph."""
    selected = tuple(item for item in statements if item.graph == pin.ontology_graph)
    if pin.ontology_graph is not None and not selected:
        raise InvalidOntologyError(message="Select a named graph present in the original dataset.")
    headers = {
        item.subject
        for item in selected
        if item.predicate == _RDF_TYPE and item.object == _OWL_ONTOLOGY
    }
    has_header = not headers if pin.ontology_iri is None else pin.ontology_iri in headers
    versions = {
        item.object
        for item in selected
        if item.predicate == _OWL_VERSION and item.subject == pin.ontology_iri
    }
    if not has_header or versions != (set() if pin.version_iri is None else {pin.version_iri}):
        raise InvalidOntologyError(
            message="Match the declared ontology and version IRIs in the selected graph."
        )
    imports: set[Iri] = set()
    terms: set[OntologyTermReference] = set()
    for item in selected:
        if item.predicate == _OWL_IMPORT:
            if item.subject not in headers or not isinstance(item.object, Iri):
                raise InvalidOntologyError(
                    message="Use exact IRI imports on the selected ontology header."
                )
            imports.add(item.object)
        if (
            item.predicate == _RDF_TYPE
            and isinstance(item.subject, Iri)
            and isinstance(item.object, Iri)
            and (kind := _KIND_BY_IRI.get(item.object.value)) is not None
        ):
            terms.add(OntologyTermReference(source=pin, term_iri=item.subject, entity_kind=kind))
    return (
        tuple(sorted(terms, key=lambda item: (item.term_iri.value, item.entity_kind.value))),
        tuple(sorted(imports, key=lambda item: item.value)),
    )
