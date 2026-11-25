"""Immutable asserted RDF datasets, selected graph declarations and parser provenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.module_capabilities import ModuleExtractionSupport
from domain_kernel.shared.domain.ontology_assets import (
    Iri,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologySyntax,
    OntologyTermReference,
)
from domain_kernel.shared.domain.ontology_errors import InvalidOntologyError
from domain_kernel.shared.domain.rdf import OntologyStatement, statement_key
from domain_kernel.shared.domain.reasoning_capabilities import ReasoningSupport
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

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


@dataclass(frozen=True, kw_only=True)
class OntologyDocument:
    """Original serialization and its exact declared identity."""

    pin: OntologyDocumentPin
    syntax: OntologySyntax
    payload: bytes = field(repr=False)

    def __post_init__(self) -> None:
        """Require exact original bytes and immutable declared identity."""
        RuntimeTypeValidation.require_exact(
            value=self.pin, expected=OntologyDocumentPin, field="Ontology document pin"
        )
        RuntimeTypeValidation.require_exact(
            value=self.syntax, expected=OntologySyntax, field="Ontology syntax"
        )
        RuntimeTypeValidation.require_exact(
            value=self.payload, expected=bytes, field="Ontology bytes"
        )
        if self.pin.content_hash != hash_bytes(content=self.payload):
            raise InvalidOntologyError(message="Restore the original ontology bytes for this pin.")


@dataclass(frozen=True, kw_only=True)
class OntologyLimits:
    """Independent budgets for supplied bytes, closure expansion and parsing time."""

    max_bytes: int = 64 * 1024 * 1024
    max_documents: int = 256
    max_statements: int = 1_000_000
    timeout_ms: int = 60_000

    def __post_init__(self) -> None:
        """Require positive finite integer limits."""
        for value in (self.max_bytes, self.max_documents, self.max_statements, self.timeout_ms):
            if type(value) is not int or value < 1:
                raise ValueError("Set positive integer ontology limits")


@dataclass(frozen=True, kw_only=True)
class OntologyCapabilities:
    """Identity and supported transformations of an explicitly selected adapter."""

    adapter_id: str
    adapter_version: str
    extraction: Sequence[ModuleExtractionSupport] = field(
        default=(), metadata={"wire_omit_empty": True}
    )
    reasoning: Sequence[ReasoningSupport] = field(default=(), metadata={"wire_omit_empty": True})
    parse_syntaxes: Sequence[OntologySyntax] = ()
    serialize_syntaxes: Sequence[OntologySyntax] = ()
    datatypes: Sequence[Iri] = ()
    feature_ids: Sequence[str] = ()

    def __post_init__(self) -> None:
        """Capture advertised capabilities as immutable typed choices."""
        TextValidation.require_text(value=self.adapter_id, field="Ontology adapter ID")
        TextValidation.require_text(value=self.adapter_version, field="Ontology adapter version")
        extraction = SequenceValidation.snapshot_sequence(
            items=self.extraction, item_type=ModuleExtractionSupport, field="Module capabilities"
        )
        if len({(item.method, item.profile, item.regime) for item in extraction}) != len(
            extraction
        ):
            raise ValueError("Advertise one extraction contract per method, profile and regime")
        object.__setattr__(self, "extraction", extraction)
        reasoning = SequenceValidation.snapshot_sequence(
            items=self.reasoning, item_type=ReasoningSupport, field="Reasoning capabilities"
        )
        if len({(item.profile, item.regime, item.task) for item in reasoning}) != len(reasoning):
            raise ValueError("Advertise one result contract per reasoning profile, regime and task")
        object.__setattr__(self, "reasoning", reasoning)
        for name, values in (
            ("parse_syntaxes", self.parse_syntaxes),
            ("serialize_syntaxes", self.serialize_syntaxes),
        ):
            object.__setattr__(
                self,
                name,
                SequenceValidation.snapshot_sequence(
                    items=values, item_type=OntologySyntax, field=name
                ),
            )
        object.__setattr__(
            self,
            "datatypes",
            SequenceValidation.snapshot_sequence(
                items=self.datatypes,
                item_type=Iri,
                field="Supported datatypes",
            ),
        )
        object.__setattr__(
            self,
            "feature_ids",
            SequenceValidation.snapshot_sequence(
                items=self.feature_ids,
                item_type=str,
                field="Semantic feature IDs",
            ),
        )


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


@dataclass(frozen=True, kw_only=True)
class ParsedOntology:
    """A pinned document's full asserted dataset and selected declarations."""

    document: OntologyDocument
    parser_id: str
    parser_version: str
    statements: Sequence[OntologyStatement] = field(repr=False)
    terms: Sequence[OntologyTermReference]
    import_iris: Sequence[Iri] = ()
    context_iris: Sequence[Iri] = ()

    def __post_init__(self) -> None:
        """Freeze statements and verify declared term and import inventories."""
        RuntimeTypeValidation.require_exact(
            value=self.document, expected=OntologyDocument, field="Parsed document"
        )
        TextValidation.require_text(value=self.parser_id, field="Ontology parser ID")
        TextValidation.require_text(value=self.parser_version, field="Ontology parser version")
        statements = SequenceValidation.snapshot_sequence(
            items=self.statements,
            item_type=OntologyStatement,
            field="Ontology statements",
        )
        statements = tuple(sorted(set(statements), key=lambda item: statement_key(statement=item)))
        object.__setattr__(self, "statements", statements)
        terms = SequenceValidation.snapshot_sequence(
            items=self.terms,
            item_type=OntologyTermReference,
            field="Declared ontology terms",
        )
        imports = SequenceValidation.snapshot_sequence(
            items=self.import_iris, item_type=Iri, field="Ontology imports"
        )
        if (terms, imports) != declaration_inventory(pin=self.document.pin, statements=statements):
            raise InvalidOntologyError(
                message="Match term and import inventories to the selected graph."
            )
        object.__setattr__(self, "terms", terms)
        object.__setattr__(self, "import_iris", imports)
        contexts = SequenceValidation.snapshot_sequence(
            items=self.context_iris, item_type=Iri, field="JSON-LD contexts"
        )
        if tuple(sorted(set(contexts), key=lambda value: value.value)) != contexts:
            raise InvalidOntologyError(message="Supply each used context once in IRI order.")
        object.__setattr__(self, "context_iris", contexts)
