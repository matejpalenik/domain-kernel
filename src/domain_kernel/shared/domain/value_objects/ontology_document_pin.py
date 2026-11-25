"""Exact declared identity of a selected ontology document and graph."""

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.blank_node import BlankNode
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class OntologyDocumentPin:
    """Exact declared identity of a selected ontology document and graph."""

    document_iri: Iri
    content_hash: ContentHash
    ontology_iri: Iri | None = None
    version_iri: Iri | None = None
    ontology_graph: Iri | BlankNode | None = None

    def __post_init__(self) -> None:
        """Check complete nominal pin metadata without loading the document."""
        RuntimeTypeValidation.require_exact(
            value=self.document_iri, expected=Iri, field="Document IRI"
        )
        RuntimeTypeValidation.require_exact(
            value=self.content_hash, expected=ContentHash, field="Document hash"
        )
        if self.ontology_iri is not None:
            RuntimeTypeValidation.require_exact(
                value=self.ontology_iri, expected=Iri, field="Ontology IRI"
            )
        if self.version_iri is not None:
            RuntimeTypeValidation.require_exact(
                value=self.version_iri, expected=Iri, field="Ontology version IRI"
            )
            if self.ontology_iri is None:
                raise ValueError("A version IRI requires the corresponding ontology IRI")
        if self.ontology_graph is not None and type(self.ontology_graph) not in (Iri, BlankNode):
            raise TypeError("Ontology graph must be an Iri or BlankNode")
