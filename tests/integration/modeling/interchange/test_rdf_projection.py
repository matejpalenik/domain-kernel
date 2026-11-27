"""Verify RDF graph placement and exact SHACL meanings from a published model."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AttributeDefinition,
    BusinessCode,
    Client,
    ClientConfiguration,
    CollectionKind,
    CollectionSemanticsObligation,
    Count,
    DomainModelBuilder,
    Iri,
    KeyDefinition,
    LabelText,
    MeaningText,
    ModelKind,
    OntologyDocument,
    OntologyDocumentPin,
    OntologySyntax,
    ProjectionBlockedError,
    ProjectionFeature,
    RdfProjectionRequest,
    RdfSyntax,
    ReferencePack,
    ReferencePackSpec,
    SemanticGraphRole,
    ValueSetMember,
    ValueSetMembership,
    load_ontology,
    project_semantics,
)
from domain_kernel.modeling.domain.interchange import RDF_VOCABULARY
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from domain_kernel import DomainModelBundle, Model, OntologyClosure

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
pytest.importorskip("rdflib")

_BASE = Iri(value="https://example.org/domains/")
_SH = "http://www.w3.org/ns/shacl#"


async def _publish(
    *,
    tmp_path: Path,
    market: CollectionKind = CollectionKind.SET,
    fields: Sequence[AttributeDefinition] = (),
    terms: OntologyClosure | None = None,
) -> tuple[Model, DomainModelBundle]:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="editor",
        name="recruitment",
    )
    pack = (
        None
        if terms is None
        else ReferencePack.compose(
            spec=ReferencePackSpec(
                key="example.time",
                version="1.0.0",
                title="Time terms",
                applicability="Permitted measurement codes",
                provenance="Asserted fixture vocabulary",
                license="Apache-2.0",
                ontologies=[terms],
            ),
            actor="editor",
            reason="Materialize the exact source terms.",
        ).pack
    )
    model = await project.create_model(
        actor="editor",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Approved recruitment data.",
        reference_pack=pack,
    )
    builder = DomainModelBuilder(model_info=model.info)
    hour = builder.add_unit(name="hour", meaning="Elapsed hour.", symbol="h")
    duration_term = None
    members = [
        ValueSetMember(
            code=BusinessCode(value="h"),
            label=LabelText(value="Hour"),
            meaning=MeaningText(value="Elapsed hour."),
            unit=hour,
        )
    ]
    if terms is not None:
        duration_term = next(
            term for term in terms.documents[0].terms if term.term_iri.value.endswith("#Duration")
        )
        minute = next(
            term for term in terms.documents[0].terms if term.term_iri.value.endswith("#Minute")
        )
        members.append(
            ValueSetMember(
                code=BusinessCode(value="min"),
                label=LabelText(value="Minute"),
                meaning=MeaningText(value="Elapsed minute."),
                ontology_term=minute,
            )
        )
    units = builder.add_value_set(
        name="duration-unit",
        meaning="Permitted turnaround unit.",
        membership=ValueSetMembership.CLOSED,
        members=members,
    )
    _ = builder.add_quantity(
        name="duration",
        meaning="Elapsed turnaround time.",
        units=units,
        quantity_kind=duration_term,
    )
    identifier = AttributeDefinition.string(name="identifier", required=True)
    _ = builder.add_concept(
        name="system",
        meaning="A recruitment system.",
        attributes=[
            identifier,
            *fields,
            AttributeDefinition.string(name="purpose", collection=market, max_items=Count(value=3)),
        ],
        keys=[KeyDefinition(name="identity", attributes=[identifier.id])],
    )
    plan = builder.build_change_plan(reason="Approve the recruitment shape and duration unit.")
    case = await model.propose_change_plan(actor="editor", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    prepared = await model.prepare_publication(actor="editor")
    bundle = await model.publish(
        publication=prepared,
        actor="publisher",
        version="1.0.0",
        reason="Deliver the shape.",
    )
    return model, bundle


@pytest.mark.filterwarnings("ignore:ConjunctiveGraph is deprecated:DeprecationWarning")
async def test_separate_graph_roles_keep_closed_unit_codes_and_same_graph_meaning(
    tmp_path: Path,
) -> None:
    from rdflib import Graph, URIRef  # noqa: PLC0415 - Optional RDF conformance fixture.
    from rdflib.compare import isomorphic  # noqa: PLC0415 - Optional RDF conformance fixture.

    model, bundle = await _publish(tmp_path=tmp_path, market=CollectionKind.SET)
    ttl = project_semantics(bundle=bundle, base_iri=_BASE)
    jsonld = project_semantics(bundle=bundle, base_iri=_BASE, syntax=RdfSyntax.JSONLD)
    assert {item.role for item in ttl.documents} == set(SemanticGraphRole)
    assert len({item.graph_iri for item in ttl.documents}) == len(SemanticGraphRole)
    for left, right in zip(ttl.documents, jsonld.documents, strict=True):
        assert left.graph_iri == right.graph_iri
        assert left.role is right.role
        assert isomorphic(
            Graph().parse(data=left.payload, format="turtle"),
            Graph().parse(data=right.payload, format="json-ld"),
        )
    selected = next(
        item for item in ttl.documents if item.role is SemanticGraphRole.INSTANCE_SHAPES
    )
    graph = Graph().parse(data=selected.payload, format="turtle")
    assert list(graph.triples((None, URIRef(f"{_SH}in"), None)))
    assert not any(
        isinstance(item, CollectionSemanticsObligation) for item in ttl.consumer_obligations
    )
    stored = await model.export(
        actor="publisher",
        bundle=bundle,
        store="artifacts",
        path="published.ttl",
        request=RdfProjectionRequest(base_iri=_BASE),
        role=SemanticGraphRole.INSTANCE_SHAPES,
    )
    assert stored.semantic is not None
    assert stored.semantic.graph_iri == selected.graph_iri
    assert stored.semantic.role is selected.role
    assert stored.content_hash == Hashing.hash_bytes(content=selected.payload)
    assert (tmp_path / ".domain-kernel/artifacts" / stored.key).read_bytes() == selected.payload
    assert stored.consumer_obligations == ttl.consumer_obligations


async def test_ontology_role_cannot_bypass_blocked_instance_shapes(tmp_path: Path) -> None:
    model, bundle = await _publish(tmp_path=tmp_path, market=CollectionKind.LIST)
    with pytest.raises(ProjectionBlockedError) as blocked:
        _ = await model.export(
            actor="publisher",
            bundle=bundle,
            store="artifacts",
            path="invalid.ttl",
            request=RdfProjectionRequest(base_iri=_BASE),
            role=SemanticGraphRole.ONTOLOGY,
        )
    assert not blocked.value.assessment.exportable
    assert not (tmp_path / ".domain-kernel/artifacts").exists()
    assert await model.get_version(version=bundle.version) == bundle


async def test_shacl_counts_match_supported_required_and_optional_sets(tmp_path: Path) -> None:
    required_set = AttributeDefinition.decimal(
        name="estimates",
        required=True,
        collection=CollectionKind.SET,
        min_items=Count(value=1),
        max_items=Count(value=2),
    )
    model, bundle = await _publish(tmp_path=tmp_path, fields=[required_set])
    projection = project_semantics(bundle=bundle, base_iri=_BASE)
    first = bundle.get_concept(name="system")
    selected = next(
        item for item in projection.documents if item.role is SemanticGraphRole.INSTANCE_SHAPES
    )
    shape_path = tmp_path / "instance-shapes.ttl"
    _ = shape_path.write_bytes(selected.payload)
    terms = [
        next(
            identity.term_iri.value
            for identity in projection.identities
            if identity.definition.definition_id == first.id and identity.local_path == path
        )
        for path in (
            (),
            ("attributes", first.get_attribute(name="identifier").id.value),
            ("attributes", required_set.id.value),
            ("attributes", first.get_attribute(name="purpose").id.value),
        )
    ]
    assert [
        x.attribute
        for x in projection.consumer_obligations
        if isinstance(x, CollectionSemanticsObligation)
    ] == [required_set.id]
    result = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-I",
            "-c",
            """
import sys
from pyshacl import validate
from rdflib import Graph, Literal, RDF, URIRef, XSD
from pathlib import Path
shape_path, class_id, id_field, estimates, purposes = sys.argv[1:]
shapes = Graph().parse(data=Path(shape_path).read_bytes(), format='turtle')
focus = URIRef('https://example.org/system')
for ident, amounts, use_cases, expected in (
    (None, ['1'], (), False),
    ('a', [], (), False),
    ('a', ['1'], (), True),
    ('a', ['1'], ('screening',), True),
    ('a', ['1', '2', '3'], (), False),
):
    records = Graph()
    records.add((focus, RDF.type, URIRef(class_id)))
    if ident is not None:
        records.add((focus, URIRef(id_field), Literal(ident)))
    for value in amounts:
        records.add((focus, URIRef(estimates), Literal(value, datatype=XSD.decimal)))
    for value in use_cases:
        records.add((focus, URIRef(purposes), Literal(value)))
    assert validate(records, shacl_graph=shapes, do_owl_imports=False)[0] is expected
""",
            str(shape_path),
            *terms,
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert await model.get_version(version=bundle.version) == bundle


async def test_rdf_blocks_required_empty_and_optional_nonempty_sets(tmp_path: Path) -> None:
    fields = [
        AttributeDefinition.string(
            name="always-present", required=True, collection=CollectionKind.SET
        ),
        AttributeDefinition.string(
            name="when-present",
            collection=CollectionKind.SET,
            min_items=Count(value=1),
        ),
    ]
    _, bundle = await _publish(tmp_path=tmp_path, fields=fields)
    result = bundle.assess_projection(request=RdfProjectionRequest(base_iri=_BASE))
    assert not result.exportable
    assert {
        finding.location.member
        for finding in result.findings
        if finding.feature is ProjectionFeature.FIELD_PRESENCE and finding.next_steps
    } == {field.id for field in fields}


async def test_mixed_quantity_retains_codes_pins_and_stable_unit_iri(tmp_path: Path) -> None:
    from rdflib import RDF, RDFS, Graph, Literal, URIRef  # noqa: PLC0415 - Optional test adapter.

    original = b"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix t: <https://example.org/time#> .
        t:Duration a owl:NamedIndividual .
        t:Minute a owl:NamedIndividual .
    """
    closure = load_ontology(
        document=OntologyDocument(
            pin=OntologyDocumentPin(
                document_iri=Iri(value="https://example.org/time.ttl"),
                content_hash=Hashing.hash_bytes(content=original),
            ),
            syntax=OntologySyntax.TURTLE,
            payload=original,
        )
    )
    model, bundle = await _publish(tmp_path=tmp_path, terms=closure)
    projected = project_semantics(bundle=bundle, base_iri=_BASE)
    graphs = {
        item.role: Graph().parse(data=item.payload, format="turtle") for item in projected.documents
    }
    assert projected.ontologies == (closure,)
    assert not projected.ontology_dependencies
    dk = RDF_VOCABULARY.value
    ontology, metadata = (
        graphs[SemanticGraphRole.ONTOLOGY],
        graphs[SemanticGraphRole.MODEL_METADATA],
    )
    unit = await model.get_unit(name="hour")
    first_uri = next(
        item.term_iri for item in projected.identities if item.definition.definition_id == unit.id
    )
    assert (URIRef(first_uri.value), RDF.type, URIRef(f"{dk}Unit")) in ontology
    assert list(
        metadata.triples(
            (None, URIRef(f"{dk}quantityKind"), URIRef("https://example.org/time#Duration"))
        )
    )
    assert list(
        metadata.triples(
            (None, URIRef(f"{dk}provenanceTerm"), URIRef("https://example.org/time#Minute"))
        )
    )
    assert list(
        graphs[SemanticGraphRole.INSTANCE_SHAPES].triples((None, RDF.first, Literal("min")))
    )
    assert not list(ontology.triples((None, URIRef("http://www.w3.org/2002/07/owl#sameAs"), None)))

    latest = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(
        name="recruitment"
    )
    overview = await latest.get_model(name="observed")
    builder = DomainModelBuilder(model_info=overview.info)
    builder.edit_unit(unit=unit, display_name="Clock hour", symbol="hr")
    plan = builder.build_change_plan(
        reason="Use the receiver's display labels for the elapsed hour."
    )
    case = await overview.propose_change_plan(actor="editor", plan=plan)
    _ = await overview.decide_review(
        actor="reviewer", case=case, decision=Accept(reason=plan.reason)
    )
    prepared = await overview.prepare_publication(actor="editor")
    revised = await overview.publish(
        publication=prepared,
        actor="publisher",
        version="1.1.0",
        reason="Update unit labels.",
    )
    newer = project_semantics(bundle=revised, base_iri=_BASE)
    role = next(doc for doc in newer.documents if doc.role is SemanticGraphRole.ONTOLOGY)
    newer_graph = Graph().parse(data=role.payload, format="turtle")
    assert (URIRef(first_uri.value), RDFS.label, Literal("Clock hour")) in newer_graph
    assert (URIRef(first_uri.value), URIRef(f"{dk}symbol"), Literal("hr")) in newer_graph


async def test_rdf_projects_exact_dependency_versions(tmp_path: Path) -> None:
    _, upstream = await _publish(tmp_path=tmp_path)
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(
        name="recruitment",
    )
    review = await project.create_model(
        actor="author",
        name="review",
        kind=ModelKind.PROPOSED,
        description="Use the exact system profile.",
        dependencies=[upstream.model_version],
    )
    builder = DomainModelBuilder(model_info=review.info)
    _ = builder.add_concept(name="review", meaning="A review of the observed model.")
    plan = builder.build_change_plan(reason="Review the dependency context.")
    case = await review.propose_change_plan(actor="author", plan=plan)
    _ = await review.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    prepared = await review.prepare_publication(actor="editor")
    released = await review.publish(
        publication=prepared,
        actor="publisher",
        version="1.0.0",
        reason="Publish the review.",
    )
    projection = project_semantics(bundle=released, base_iri=_BASE)
    assert projection.dependencies == (upstream.model_version,)
    assert {doc.model for doc in projection.documents} == {
        released.model_version,
        upstream.model_version,
    }
    assert {doc.role for doc in projection.documents if doc.model == upstream.model_version} == set(
        SemanticGraphRole
    )
    root_metadata = next(
        doc
        for doc in projection.documents
        if doc.model == released.model_version and doc.role is SemanticGraphRole.MODEL_METADATA
    )
    assert upstream.content_hash.value.encode("ascii") in root_metadata.payload
