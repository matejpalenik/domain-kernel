"""Exact identifiers for optional authored ontology bindings."""

import re
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Literal

from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, require_text

_IRI_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_INVALID_IRI_CHAR = re.compile(r'[\x00-\x20\x7f-\x9f\ud800-\udfff<>"{}|\\^`]|%(?![0-9A-Fa-f]{2})')


@dataclass(frozen=True, kw_only=True)
class Iri:
    """Preserve the exact spelling of an absolute resource identifier."""

    value: str
    kind: Literal["iri"] = "iri"

    def __post_init__(self) -> None:
        """Reject relative or malformed IRIs without dereferencing resources."""
        require_text(value=self.value, field="IRI")
        require_exact(value=self.kind, expected=str, field="IRI kind")
        if self.kind != "iri":
            raise ValueError("IRI kind must be 'iri'")
        if (
            _IRI_SCHEME.match(self.value) is None
            or _INVALID_IRI_CHAR.search(self.value)
            or any(character.isspace() for character in self.value)
        ):
            raise ValueError("Use an absolute IRI with a valid scheme and spelling")


@dataclass(frozen=True, kw_only=True)
class BlankNode:
    """A graph name scoped to one pinned document."""

    id: str
    kind: Literal["blank_node"] = "blank_node"

    def __post_init__(self) -> None:
        """Require an exact node identifier and wire tag."""
        require_text(value=self.id, field="Blank node ID")
        require_exact(value=self.kind, expected=str, field="Blank node kind")
        if self.kind != "blank_node":
            raise ValueError("Blank node kind must be 'blank_node'")


@unique
class OntologyEntityKind(StrEnum):
    """Declared role of a term in a pinned document graph."""

    CLASS = "class"
    OBJECT_PROPERTY = "object_property"
    DATA_PROPERTY = "data_property"
    ANNOTATION_PROPERTY = "annotation_property"
    RDF_PROPERTY = "rdf_property"
    DATATYPE = "datatype"
    INDIVIDUAL = "individual"
    SKOS_CONCEPT = "skos_concept"


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
        require_exact(value=self.document_iri, expected=Iri, field="Document IRI")
        require_exact(value=self.content_hash, expected=ContentHash, field="Document hash")
        if self.ontology_iri is not None:
            require_exact(value=self.ontology_iri, expected=Iri, field="Ontology IRI")
        if self.version_iri is not None:
            require_exact(value=self.version_iri, expected=Iri, field="Ontology version IRI")
            if self.ontology_iri is None:
                raise ValueError("A version IRI requires the corresponding ontology IRI")
        if self.ontology_graph is not None and type(self.ontology_graph) not in (Iri, BlankNode):
            raise TypeError("Ontology graph must be an Iri or BlankNode")


@dataclass(frozen=True, kw_only=True)
class OntologyTermReference:
    """Exact declared term and kind in one pinned document graph."""

    source: OntologyDocumentPin
    term_iri: Iri
    entity_kind: OntologyEntityKind

    def __post_init__(self) -> None:
        """Preserve typed provenance without claiming the term has been materialized."""
        require_exact(value=self.source, expected=OntologyDocumentPin, field="Ontology source")
        require_exact(value=self.term_iri, expected=Iri, field="Ontology term IRI")
        require_exact(value=self.entity_kind, expected=OntologyEntityKind, field="Ontology kind")


def require_unit_term(*, term: OntologyTermReference) -> None:
    """Require a declared individual or SKOS concept for a unit or quantity kind."""
    require_exact(value=term, expected=OntologyTermReference, field="Unit or quantity term")
    if term.entity_kind not in (OntologyEntityKind.INDIVIDUAL, OntologyEntityKind.SKOS_CONCEPT):
        raise ValueError("Unit and quantity terms must be individuals or SKOS concepts")
