"""Worker process for RDFLib. All input is verified original bytes on stdin."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from itertools import count
from typing import TYPE_CHECKING, Never, TypedDict, final, override
from uuid import UUID
from xml.parsers import expat

import rdflib
from rdflib import BNode, Dataset, Literal, URIRef
from rdflib import term as rdf_term
from rdflib.plugins.parsers import notation3
from rdflib.plugins.shared.jsonld import context
from rdflib.plugins.stores.memory import Memory

from domain_kernel._shared.domain.ontology_assets import BlankNode, Iri, OntologySyntax
from domain_kernel._shared.domain.ontology_documents import (
    OntologyDocument,
    ParsedOntology,
    declaration_inventory,
)
from domain_kernel._shared.domain.ontology_errors import (
    InvalidOntologyError,
    UnsupportedCapabilityError,
)
from domain_kernel._shared.domain.rdf import OntologyStatement, RdfLiteral
from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel.modeling.infrastructure.rdf_messages import ParseRdf, WriteRdf
from domain_kernel.modeling.infrastructure.rdflib_adapter import RDFLIB_FORMATS
from domain_kernel.shared.errors import ResourceLimitError
from domain_kernel.shared.hashing import hash_bytes, hash_json

if TYPE_CHECKING:
    from rdflib.graph import Graph
    from rdflib.term import Node

    from domain_kernel.shared.hashing import JsonValue


class _DatasetOptions(TypedDict, total=False):
    bnode_context: dict[str, BNode]


@final
class _BoundedMemory(Memory):
    def __init__(self, *, maximum: int) -> None:
        super().__init__()
        self._remaining = maximum

    @override
    def add(self, triple: tuple[Node, Node, Node], context: Graph, quoted: bool = False) -> None:
        if self._remaining < 1:
            raise ResourceLimitError
        self._remaining -= 1
        super().add(triple=triple, context=context, quoted=quoted)


def _block_network(event: str, _arguments: tuple[object, ...]) -> None:
    if event.startswith("socket."):
        raise InvalidOntologyError(message="Supply every ontology dependency as pinned bytes.")


def _block_doctype(*_arguments: object) -> Never:
    raise InvalidOntologyError(message="Supply RDF/XML without a DTD or entity declarations.")


def _initialize_parser(*, command: ParseRdf) -> None:
    sequence = count(start=1)
    scope = hash_json(
        value=(
            command.document.pin.document_iri.value,
            command.document.pin.content_hash.value,
        )
    ).value.removeprefix("sha256:")

    def deterministic_node() -> UUID:
        return UUID(int=(int(scope[:16], 16) << 64) | next(sequence))

    # RDFLib uses process-global switches and random node labels. Isolate these
    # deterministic settings to a single input and keep the caller's interpreter untouched.
    rdflib.NORMALIZE_LITERALS = False
    rdf_term.uuid4 = deterministic_node  # pyright: ignore[reportPrivateImportUsage]
    notation3.uuid4 = deterministic_node  # pyright: ignore[reportPrivateImportUsage]
    graph = command.document.pin.ontology_graph
    if isinstance(graph, BlankNode) and command.document.syntax is OntologySyntax.TRIG:
        previous_label = notation3.SinkParser.anonymousNode

        def named_node(self: notation3.SinkParser, ln: str) -> BNode:
            return BNode(ln) if ln == graph.id else previous_label(self, ln)

        notation3.SinkParser.anonymousNode = named_node
    if command.document.syntax is OntologySyntax.RDFXML:
        guard = expat.ParserCreate()
        guard.StartDoctypeDeclHandler = _block_doctype
        # Expat takes the end-of-document flag positionally.
        _ = guard.Parse(command.document.payload, True)  # noqa: FBT003


def _identity(*, node: object) -> Iri | BlankNode:
    if isinstance(node, URIRef):
        return Iri(value=str(node))
    if isinstance(node, BNode):
        return BlankNode(id=str(node))
    raise InvalidOntologyError(message="Use RDF 1.1 resource and blank-node identifiers.")


def _object(*, node: object) -> Iri | BlankNode | RdfLiteral:
    if isinstance(node, Literal):
        return RdfLiteral(
            value=str(node),
            datatype=Iri(value=str(node.datatype))
            if node.datatype is not None and node.language is None
            else None,
            language=node.language,
        )
    return _identity(node=node)


def _parse(*, command: ParseRdf) -> ParsedOntology:
    _initialize_parser(command=command)
    contexts: dict[str, list[OntologyDocument]] = {}
    used: set[Iri] = set()
    for item in command.resources:
        contexts.setdefault(item.pin.document_iri.value, []).append(item)

    def supplied_context(source: str) -> tuple[object, None]:
        choices = contexts.get(source)
        if choices is None or len(choices) != 1:
            raise InvalidOntologyError(
                message="Provide the requested JSON-LD context as exact pinned bytes."
            )
        selected = choices[0]
        used.add(selected.pin.document_iri)
        value: JsonValue = json.loads(selected.payload)  # pyright: ignore[reportAny]
        return value, None

    # Limit RDFLib's remote-context resolver to caller-supplied verified bytes.
    context.source_to_json = supplied_context  # pyright: ignore[reportPrivateImportUsage]
    document = command.document
    dataset = Dataset(store=_BoundedMemory(maximum=command.limits.max_statements))
    options: _DatasetOptions = {}
    graph = document.pin.ontology_graph
    if isinstance(graph, BlankNode) and document.syntax is OntologySyntax.NQUADS:
        options["bnode_context"] = {graph.id: BNode(graph.id)}
    _ = dataset.parse(
        data=document.payload,
        publicID=document.pin.document_iri.value,
        format=RDFLIB_FORMATS[document.syntax],
        **options,
    )
    assertions = tuple(
        OntologyStatement(
            subject=_identity(node=subject),
            predicate=Iri(value=str(predicate)),
            object=_object(node=obj),
            graph=None
            if graph is None or graph == dataset.default_graph.identifier
            else _identity(node=graph),
        )
        for subject, predicate, obj, graph in dataset.quads((None, None, None, None))
    )
    terms, imports = declaration_inventory(pin=document.pin, statements=assertions)
    return ParsedOntology(
        document=document,
        parser_id="rdflib",
        parser_version=rdflib.__version__,
        statements=assertions,
        terms=terms,
        import_iris=imports,
        context_iris=tuple(sorted(used, key=lambda item: item.value)),
    )


def _rdf_resource(*, node: Iri | BlankNode) -> URIRef | BNode:
    return URIRef(node.value) if isinstance(node, Iri) else BNode(node.id)


def _rdf_object(*, node: Iri | BlankNode | RdfLiteral) -> URIRef | BNode | Literal:
    if isinstance(node, RdfLiteral):
        datatype = URIRef(node.datatype.value) if node.datatype is not None else None
        return Literal(node.value, lang=node.language, datatype=datatype, normalize=False)
    return _rdf_resource(node=node)


def _serialize(*, command: WriteRdf) -> OntologyDocument:
    statements = command.ontology.statements
    if command.syntax not in (
        OntologySyntax.TRIG,
        OntologySyntax.NQUADS,
        OntologySyntax.JSONLD,
    ) and any(assertion.graph is not None for assertion in statements):
        raise UnsupportedCapabilityError(
            message="Choose a dataset syntax to preserve every named graph."
        )
    dataset = Dataset(store=_BoundedMemory(maximum=command.limits.max_statements))
    for assertion in statements:
        graph = (
            dataset.default_graph
            if assertion.graph is None
            else dataset.graph(identifier=_rdf_resource(node=assertion.graph))
        )
        _ = graph.add(
            (
                _rdf_resource(node=assertion.subject),
                URIRef(assertion.predicate.value),
                _rdf_object(node=assertion.object),
            )
        )
    payload: bytes = dataset.serialize(format=RDFLIB_FORMATS[command.syntax], encoding="utf-8")
    if len(payload) > command.limits.max_bytes:
        raise ResourceLimitError
    pin = replace(
        command.ontology.document.pin,
        document_iri=command.document_iri,
        content_hash=hash_bytes(content=payload),
    )
    return OntologyDocument(pin=pin, syntax=command.syntax, payload=payload)


def main() -> None:
    """Execute a single ontology operation with sanitized process status."""
    sys.addaudithook(_block_network)
    command = sys.argv[1]
    data = sys.stdin.buffer.read()
    try:
        if command == "parse":
            parsed = _parse(
                command=read_record(content=data, expected=ParseRdf, root_type=ParseRdf)
            )
            _ = sys.stdout.buffer.write(record_bytes(value=parsed))
        elif command == "serialize":
            written = _serialize(
                command=read_record(content=data, expected=WriteRdf, root_type=WriteRdf)
            )
            _ = sys.stdout.buffer.write(record_bytes(value=written))
    except ResourceLimitError:
        sys.exit(3)
    except UnsupportedCapabilityError:
        sys.exit(4)
    except Exception:  # noqa: BLE001 - A parser process never returns raw provider data.
        sys.exit(2)


if __name__ == "__main__":
    main()
