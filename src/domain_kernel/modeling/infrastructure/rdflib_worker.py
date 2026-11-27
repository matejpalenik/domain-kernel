"""Worker process for RDFLib. All input is verified original bytes on stdin."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from importlib import import_module
from itertools import count
from typing import TYPE_CHECKING, Never, Protocol, TypedDict, final, override, runtime_checkable
from uuid import UUID
from xml.parsers import expat

import rdflib
from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib import term as rdf_term
from rdflib.plugins.parsers import notation3
from rdflib.plugins.shared.jsonld import context
from rdflib.plugins.stores.memory import Memory

from domain_kernel.modeling.application.shacl_shapes import CONTROLLED_SHAPE_PREDICATES
from domain_kernel.modeling.domain.interchange import RdfSyntax
from domain_kernel.modeling.infrastructure.rdf_messages import (
    CheckShacl,
    ParseRdf,
    RenderedRdfGraphs,
    RenderRdfGraphs,
    ShaclResults,
    WriteRdf,
)
from domain_kernel.modeling.infrastructure.rdflib_adapter import RDFLIB_FORMATS
from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.domain.enums.ontology_syntax import OntologySyntax
from domain_kernel.shared.domain.errors.invalid_ontology_error import InvalidOntologyError
from domain_kernel.shared.domain.policies.ontology_declarations_policy import (
    OntologyDeclarationsPolicy,
)
from domain_kernel.shared.domain.value_objects.blank_node import BlankNode
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.ontology_document import OntologyDocument
from domain_kernel.shared.domain.value_objects.ontology_statement import OntologyStatement
from domain_kernel.shared.domain.value_objects.parsed_ontology import ParsedOntology
from domain_kernel.shared.domain.value_objects.rdf_literal import RdfLiteral
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.errors.unsupported_capability_error import (
    UnsupportedCapabilityError,
)
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rdflib.term import Node

    from domain_kernel.modeling.infrastructure.rdf_messages import ShaclResult
    from domain_kernel.shared.json_value import JsonValue


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
    scope = Hashing.hash_json(
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
    terms, imports = OntologyDeclarationsPolicy.declaration_inventory(
        pin=document.pin, statements=assertions
    )
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
        content_hash=Hashing.hash_bytes(content=payload),
    )
    return OntologyDocument(pin=pin, syntax=command.syntax, payload=payload)


def _sort_jsonld(*, value: JsonValue, property_name: str | None = None) -> JsonValue:
    if isinstance(value, dict):
        return {key: _sort_jsonld(value=item, property_name=key) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        items = tuple(_sort_jsonld(value=item) for item in value)
        return items if property_name == "@list" else tuple(sorted(items, key=_json_order))
    return value


def _json_order(value: JsonValue) -> bytes:
    return CanonicalJson.encode(value=value)


def _graph(*, rows: Sequence[OntologyStatement]) -> Graph:
    graph = Graph()
    for assertion in rows:
        _ = graph.add(
            (
                _rdf_resource(node=assertion.subject),
                URIRef(assertion.predicate.value),
                _rdf_object(node=assertion.object),
            )
        )
    return graph


def _render_graph(*, rows: Sequence[OntologyStatement], syntax: RdfSyntax) -> bytes:
    graph = _graph(rows=rows)
    if syntax is RdfSyntax.TURTLE:
        # N-Triples is a Turtle subset. Sorting its one-triple lines keeps retries byte-stable.
        payload = graph.serialize(format="nt", encoding="utf-8")
        return b"\n".join(sorted(line for line in payload.splitlines() if line)) + b"\n"
    raw = graph.serialize(format="json-ld", encoding="utf-8", use_native_types=False)
    decoded: JsonValue = json.loads(raw)  # pyright: ignore[reportAny]
    return CanonicalJson.encode(value=_sort_jsonld(value=decoded))


def _render(*, command: RenderRdfGraphs) -> RenderedRdfGraphs:
    if sum(len(graph) for graph in command.statements) > command.limits.max_statements:
        raise ResourceLimitError
    payloads: list[bytes] = []
    used = 0
    for graph in command.statements:
        payload = _render_graph(rows=graph, syntax=command.syntax)
        used += len(payload)
        if used > command.limits.max_bytes:
            raise ResourceLimitError
        payloads.append(payload)
    return RenderedRdfGraphs(payloads=payloads)


@runtime_checkable
class _ShaclEngine(Protocol):
    def meta_validate(
        self,
        *,
        shacl_graph: Graph,
        inference: str,
        advanced: bool,
        js: bool,
        do_owl_imports: bool,
    ) -> tuple[object, object, object]: ...

    def validate(  # noqa: PLR0913 - Pin all required safety options.
        self,
        *,
        data_graph: Graph,
        shacl_graph: Graph,
        inference: str,
        advanced: bool,
        js: bool,
        do_owl_imports: bool,
    ) -> tuple[object, object, object]: ...


_SH = "http://www.w3.org/ns/shacl#"


def _check_result(*, result: tuple[object, object, object], code: str) -> tuple[ShaclResult, ...]:
    match result:
        case (True, Graph(), _):
            return ()
        case (False, Graph() as report, _):
            pass
        case _:
            raise InvalidOntologyError(message="Use a well-formed controlled SHACL report.")
    rows: list[ShaclResult] = []
    for row in report.subjects(
        predicate=URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
        object=URIRef(f"{_SH}ValidationResult"),
    ):
        locations: list[Iri | None] = []
        for name in ("focusNode", "sourceShape", "resultPath"):
            value = report.value(subject=row, predicate=URIRef(f"{_SH}{name}"))
            locations.append(Iri(value=str(value)) if isinstance(value, URIRef) else None)
        rows.append((code, locations[0], locations[1], locations[2]))
    return tuple(rows) or ((code, None, None, None),)


def _shacl(*, command: CheckShacl) -> ShaclResults:
    if (
        sum(map(len, (command.metadata, command.model_shapes, command.instance_shapes)))
        > command.limits.max_statements
    ):
        raise ResourceLimitError
    if any(
        row.predicate.value not in CONTROLLED_SHAPE_PREDICATES
        for assertions in (command.model_shapes, command.instance_shapes)
        for row in assertions
    ):
        raise UnsupportedCapabilityError(message="Use only the controlled SHACL Core predicates.")
    engine = import_module("pyshacl.entrypoints")
    if not isinstance(engine, _ShaclEngine):
        raise UnsupportedCapabilityError(message="Install the supported pySHACL engine.")
    model_shapes = _graph(rows=command.model_shapes)
    instance_shapes = _graph(rows=command.instance_shapes)
    invalid = tuple(
        row
        for graph in (model_shapes, instance_shapes)
        for row in _check_result(
            result=engine.meta_validate(
                shacl_graph=graph,
                inference="none",
                advanced=False,
                js=False,
                do_owl_imports=False,
            ),
            code="invalid_shacl_shape",
        )
    )
    if invalid:
        return ShaclResults(issues=invalid)
    findings = _check_result(
        result=engine.validate(
            data_graph=_graph(rows=command.metadata),
            shacl_graph=model_shapes,
            inference="none",
            advanced=False,
            js=False,
            do_owl_imports=False,
        ),
        code="shacl_violation",
    )
    return ShaclResults(issues=findings)


def main() -> None:
    """Execute a single ontology operation with sanitized process status."""
    sys.addaudithook(_block_network)
    command = sys.argv[1]
    data = sys.stdin.buffer.read()
    try:
        if command == "parse":
            parsed = _parse(
                command=RecordCodec.decode(content=data, expected=ParseRdf, root_type=ParseRdf)
            )
            _ = sys.stdout.buffer.write(RecordCodec.encode(value=parsed))
        elif command == "serialize":
            written = _serialize(
                command=RecordCodec.decode(content=data, expected=WriteRdf, root_type=WriteRdf)
            )
            _ = sys.stdout.buffer.write(RecordCodec.encode(value=written))
        elif command == "render":
            batch = RecordCodec.decode(
                content=data, expected=RenderRdfGraphs, root_type=RenderRdfGraphs
            )
            rendered = _render(command=batch)
            _ = sys.stdout.buffer.write(
                RecordCodec.encode(value=rendered, root_type=RenderedRdfGraphs)
            )
        elif command == "shacl":
            request = RecordCodec.decode(content=data, expected=CheckShacl, root_type=CheckShacl)
            checked = _shacl(command=request)
            _ = sys.stdout.buffer.write(RecordCodec.encode(value=checked, root_type=ShaclResults))
    except ResourceLimitError:
        sys.exit(3)
    except UnsupportedCapabilityError:
        sys.exit(4)
    except Exception:  # noqa: BLE001 - A parser process never returns raw provider data.
        sys.exit(2)


if __name__ == "__main__":
    main()
