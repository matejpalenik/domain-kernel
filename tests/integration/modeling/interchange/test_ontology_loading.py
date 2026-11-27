"""Check the production RDF adapter against full dataset and closure contracts."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    BlankNode,
    Client,
    ClientConfiguration,
    DomainModelBuilder,
    InvalidOntologyError,
    Iri,
    ModelKind,
    OntologyDocument,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologySyntax,
    RdfLiteral,
    ReferenceDefinition,
    ReferenceDefinitionId,
    ReferencePack,
    ReferencePackSpec,
    UnitDefinition,
    UnsupportedCapabilityError,
    load_ontology,
    serialize_ontology,
)
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

pytest.importorskip("rdflib")

_PREFIXES = b"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ex: <https://example.org/> .
"""


def _doc(  # noqa: PLR0913 - Each parameter specifies part of the exact fixture pin.
    *,
    name: str,
    payload: bytes,
    syntax: OntologySyntax = OntologySyntax.TURTLE,
    ontology: str | None = None,
    version: str | None = None,
    graph: str | None = None,
) -> OntologyDocument:
    return OntologyDocument(
        syntax=syntax,
        pin=OntologyDocumentPin(
            document_iri=Iri(value=f"https://example.org/{name}"),
            content_hash=Hashing.hash_bytes(content=payload),
            ontology_iri=None if ontology is None else Iri(value=ontology),
            version_iri=None if version is None else Iri(value=version),
            ontology_graph=None if graph is None else Iri(value=graph),
        ),
        payload=payload,
    )


def test_cycles_resolve_exact_explicit_pins_and_punning() -> None:
    root = _doc(
        name="root.ttl",
        ontology="https://example.org/root",
        payload=_PREFIXES
        + b"""
            ex:root a owl:Ontology ; owl:imports ex:upstream-v1 .
            <terms/role> a owl:Class, owl:NamedIndividual .
        """,
    )
    imported = _doc(
        name="import.ttl",
        ontology="https://example.org/upstream",
        version="https://example.org/upstream-v1",
        payload=_PREFIXES
        + b"""
            ex:upstream a owl:Ontology ; owl:versionIRI ex:upstream-v1 ; owl:imports ex:root .
            ex:role a owl:Class .
        """,
    )
    result = load_ontology(document=root, resources=[imported])
    assert result == load_ontology(document=root, resources=(imported,))
    assert {x.document.pin for x in result.documents} == {root.pin, imported.pin}
    assert {(link.source, link.target) for link in result.imports} == {
        (root.pin, imported.pin),
        (imported.pin, root.pin),
    }
    terms = next(doc.terms for doc in result.documents if doc.document.pin == root.pin)
    assert {(term.term_iri.value, term.entity_kind) for term in terms} == {
        ("https://example.org/terms/role", OntologyEntityKind.CLASS),
        ("https://example.org/terms/role", OntologyEntityKind.INDIVIDUAL),
    }
    with pytest.raises(InvalidOntologyError):
        _ = load_ontology(document=root)


def test_selected_named_graphs_preserve_full_dataset_and_lexical_literals() -> None:
    payload = (
        _PREFIXES
        + b"""
        ex:g1 {
            ex:Ont1 a owl:Ontology . ex:entity a owl:Class . _:shared ex:value "01"^^xsd:integer .
        }
        ex:g2 {
            ex:Ont2 a owl:Ontology .
            ex:entity a owl:NamedIndividual . _:shared ex:value "bonjour"@fr .
        }
    """
    )
    first = _doc(
        name="dataset.trig",
        syntax=OntologySyntax.TRIG,
        payload=payload,
        ontology="https://example.org/Ont1",
        graph="https://example.org/g1",
    )
    second = _doc(
        name="dataset.trig",
        syntax=OntologySyntax.TRIG,
        payload=payload,
        ontology="https://example.org/Ont2",
        graph="https://example.org/g2",
    )
    closure = load_ontology(document=first)
    other = load_ontology(document=second)
    assert closure.content_hash != other.content_hash
    parsed = closure.documents[0]
    assert parsed.document.payload == payload
    assert parsed.statements == load_ontology(document=first).documents[0].statements
    assert parsed.statements == other.documents[0].statements
    assert {x.graph for x in parsed.statements} == {
        first.pin.ontology_graph,
        second.pin.ontology_graph,
    }
    assert [term.entity_kind for term in parsed.terms] == [OntologyEntityKind.CLASS]
    assert [term.entity_kind for term in other.documents[0].terms] == [
        OntologyEntityKind.INDIVIDUAL
    ]
    values = [st for st in parsed.statements if isinstance(st.object, RdfLiteral)]
    assert isinstance(values[0].subject, BlankNode)
    assert values[0].subject == values[1].subject
    assert {value.object for value in values} == {
        RdfLiteral(value="bonjour", language="fr"),
        RdfLiteral(value="01", datatype=Iri(value="http://www.w3.org/2001/XMLSchema#integer")),
    }
    with pytest.raises(UnsupportedCapabilityError):
        _ = serialize_ontology(
            ontology=parsed,
            syntax=OntologySyntax.TURTLE,
            document_iri=Iri(value="https://example.org/flatten.ttl"),
        )


def test_jsonld_context_is_resolved_only_from_supplied_exact_bytes() -> None:
    context = _doc(
        name="contexts/v1.jsonld",
        syntax=OntologySyntax.JSONLD,
        payload=b'{"@context":{"@vocab":"https://example.org/","name":"https://example.org/name"}}',
    )
    root = _doc(
        name="root.jsonld",
        syntax=OntologySyntax.JSONLD,
        payload=b'{"@context":"contexts/v1.jsonld","@id":"item","name":"Alice"}',
    )
    with pytest.raises(InvalidOntologyError):
        _ = load_ontology(document=root)
    closure = load_ontology(document=root, resources=[context])
    assert closure.resources == (context,)
    assert closure.contexts[0].target == context.pin
    assert closure.documents[0].statements[0].subject == Iri(value="https://example.org/item")
    assert closure.documents[0].statements[0].object == RdfLiteral(value="Alice")


def test_unversioned_alias_is_ambiguous_and_explicit_versions_coexist() -> None:
    first = _doc(
        name="first.ttl",
        ontology="https://example.org/reference",
        version="https://example.org/v1",
        payload=_PREFIXES
        + b"""
            ex:reference a owl:Ontology ; owl:versionIRI ex:v1 .
            _:local ex:value "first" .
        """,
    )
    second = _doc(
        name="second.ttl",
        ontology="https://example.org/reference",
        version="https://example.org/v2",
        payload=_PREFIXES
        + b"""
            ex:reference a owl:Ontology ; owl:versionIRI ex:v2 .
            _:local ex:value "second" .
        """,
    )
    explicit = _doc(
        name="explicit.ttl",
        ontology="https://example.org/root",
        payload=_PREFIXES + b"ex:root a owl:Ontology ; owl:imports ex:v1, ex:v2 .",
    )
    ambiguous = _doc(
        name="ambiguous.ttl",
        ontology="https://example.org/root",
        payload=_PREFIXES + b"ex:root a owl:Ontology ; owl:imports ex:reference .",
    )
    with pytest.raises(InvalidOntologyError):
        _ = load_ontology(document=ambiguous, resources=[first, second])
    closure = load_ontology(document=explicit, resources=[first, second])
    assert closure == load_ontology(document=explicit, resources=[second, first])
    assert {binding.target for binding in closure.imports} == {first.pin, second.pin}
    nodes = [
        statement.subject
        for parsed in closure.documents
        for statement in parsed.statements
        if isinstance(statement.subject, BlankNode)
    ]
    assert nodes[0] != nodes[1]


def test_transcoding_preserves_default_and_named_graphs() -> None:
    original = _doc(
        name="document.trig",
        syntax=OntologySyntax.TRIG,
        ontology="https://example.org/root",
        payload=_PREFIXES
        + b"""
            ex:root a owl:Ontology .
            ex:schema { ex:role a owl:Class . }
        """,
    )
    parsed = load_ontology(document=original).documents[0]
    emitted = serialize_ontology(
        ontology=parsed,
        syntax=OntologySyntax.NQUADS,
        document_iri=Iri(value="https://example.org/dataset.nq"),
    )
    assert emitted.pin.content_hash != original.pin.content_hash
    assert load_ontology(document=emitted).documents[0].statements == parsed.statements


@pytest.mark.asyncio
async def test_pinned_quantity_unit_travels_with_pack_and_bundle(tmp_path: Path) -> None:
    document = _doc(
        name="units.ttl",
        ontology="https://example.org/units",
        payload=_PREFIXES
        + b"""
            ex:units a owl:Ontology .
            ex:hour a owl:NamedIndividual .
        """,
    )
    closure = load_ontology(document=document)
    hour = closure.documents[0].terms[0]
    reference = ReferenceDefinition(
        id=ReferenceDefinitionId(value="hour"),
        name="hour",
        meaning="One hour.",
        provenance="Unit distribution fixture.",
        body=UnitDefinition(symbol="h", ontology_term=hour),
    )
    spec = ReferencePackSpec(
        key="example.units",
        version="1.0.0",
        title="Pinned units",
        applicability="Turnaround durations",
        provenance="Unit distribution fixture",
        license="Apache-2.0",
        definitions=[reference],
        ontologies=[closure],
    )
    unbound = ReferencePack.compose(
        spec=replace(spec, ontologies=[]),
        actor="editor",
        reason="Use verified units.",
    )
    assert unbound.pack is None
    assert "ontology_term_missing" in {issue.code for issue in unbound.validation.issues}
    bad_kind = replace(hour, entity_kind=OntologyEntityKind.SKOS_CONCEPT)
    forged = ReferencePack.compose(
        spec=replace(
            spec,
            definitions=[
                replace(
                    reference,
                    body=UnitDefinition(symbol="h", ontology_term=bad_kind),
                )
            ],
        ),
        actor="editor",
        reason="Use verified units.",
    )
    assert forged.pack is None
    authored = ReferencePack.compose(spec=spec, actor="editor", reason="Use verified units.")
    assert authored.pack is not None
    pack = ReferencePack.deserialize(payload=authored.pack.serialize())
    assert pack.ontologies == (closure,)
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="editor",
        name="recruitment",
    )
    model = await project.create_model(
        actor="editor",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Turnaround duration vocabulary.",
        reference_pack=pack,
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_unit(
        name="hour", meaning="An hour of turnaround time.", symbol="h", ontology_term=hour
    )
    plan = builder.build_change_plan(reason="Review the pinned hour.")
    case = await model.propose_change_plan(actor="editor", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    preparation = await model.prepare_publication(actor="publisher")
    bundle = await model.publish(
        publication=preparation,
        actor="publisher",
        version="1.0.0",
        reason="Deliver verified units.",
    )
    independent = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-I",
            "-c",
            """
import sys
from domain_kernel import DomainModelBundle
bundle = DomainModelBundle.deserialize(payload=sys.stdin.buffer.read())
assert 'rdflib' not in sys.modules and 'pyshacl' not in sys.modules
term = bundle.publication.reference_pack.ontologies[0].documents[0].terms[0]
assert term.term_iri.value == 'https://example.org/hour'
""",
        ],
        input=bundle.serialize(),
        capture_output=True,
        check=True,
        cwd=tmp_path,
    )
    assert independent.returncode == 0


@pytest.mark.parametrize(
    ("syntax", "payload"),
    [
        (
            OntologySyntax.TRIG,
            b"_:named { <https://example.org/class> a <http://www.w3.org/2002/07/owl#Class> . }",
        ),
        (
            OntologySyntax.NQUADS,
            (
                b"<https://example.org/class> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
                b"<http://www.w3.org/2002/07/owl#Class> _:named ."
            ),
        ),
    ],
)
def test_select_explicit_blank_named_graph(*, syntax: OntologySyntax, payload: bytes) -> None:
    unselected = _doc(name="unnamed-dataset", syntax=syntax, payload=payload)
    graph = BlankNode(id="named")
    selected = replace(unselected, pin=replace(unselected.pin, ontology_graph=graph))
    parsed = load_ontology(document=selected).documents[0]
    assert parsed.statements[0].graph == graph
    assert parsed.terms[0].term_iri == Iri(value="https://example.org/class")
