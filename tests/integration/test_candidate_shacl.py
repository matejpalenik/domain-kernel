"""Exercise controlled model-target SHACL on reviewed unpublished candidates."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AttributeDefinition,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    ConstraintDefinition,
    ConstraintLanguage,
    ConstraintTarget,
    DomainModelBuilder,
    DomainModelBundle,
    Iri,
    ModelKind,
    PublicationBlockedError,
    RuleDefinition,
    SemanticGraphRole,
    ShaclModelValidator,
    project_semantics,
)
from domain_kernel.modeling.application.rdf_projection import RdfLibProjector
from domain_kernel.modeling.domain.interchange import RDF_VOCABULARY

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import Candidate, Model, Project

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
pytest.importorskip("pyshacl")

_HEAD = f"""@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix dk: <{RDF_VOCABULARY.value}> .
"""


async def _candidate(
    *,
    tmp_path: Path,
    unsafe: bool = False,
) -> tuple[Project, Model, Candidate]:
    client = Client(
        config=ClientConfiguration(base_dir=tmp_path),
        integrations=ClientIntegrations(validators=[ShaclModelValidator()]),
    )
    project = await client.create_project(actor="author", name="equipment")
    model = await project.create_model(
        actor="author",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Reviewed equipment definitions.",
    )
    builder = DomainModelBuilder(model_info=model.info)
    code = AttributeDefinition.string(name="asset-code", required=True)
    identity = builder.add_concept(
        name="press",
        display_name="Press",
        meaning="A workshop press.",
        attributes=[code],
    )
    root = f"definitions/{identity.value}"
    definition_rule = (
        '<shape> a sh:NodeShape ; sh:sparql [ sh:select "SELECT $this WHERE {}" ] .'
        if unsafe
        else f"""
        <shape> a sh:NodeShape ;
            sh:targetNode <{root}> ;
            sh:property [ sh:path dk:displayName ; sh:hasValue "Licensed press" ] .
        """
    )
    instance_rule = f"""
        <shape> a sh:NodeShape ;
            sh:targetClass <{root}> ;
            sh:property [ sh:path <{root}/attributes/{code.id.value}> ; sh:minCount 1 ] .
    """
    _ = builder.add_definition(
        name="equipment-entry-review",
        meaning="Confirm the metadata label and the separate operational code shape.",
        body=RuleDefinition(
            statement="A reviewed press definition identifies a licensed press.",
            constraints=[
                ConstraintDefinition(
                    id="model-label",
                    description="Require the approved display label.",
                    language=ConstraintLanguage.SHACL,
                    target=ConstraintTarget.MODEL,
                    expression=_HEAD + definition_rule,
                ),
                ConstraintDefinition(
                    id="instance-code",
                    description="Operational presses have asset codes.",
                    language=ConstraintLanguage.SHACL,
                    target=ConstraintTarget.INSTANCE,
                    expression=_HEAD + instance_rule,
                ),
            ],
        ),
    )
    plan = builder.build_change_plan(reason="Review the equipment checks.")
    case = await model.propose_change_plan(actor="author", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    return project, model, await model.compile(actor="editor")


async def test_candidate_validation_blocks_and_repairs_the_exact_model_location(
    tmp_path: Path,
) -> None:
    project, model, candidate = await _candidate(tmp_path=tmp_path)
    press = await model.get_concept(name="press")
    graphs = RdfLibProjector().validation_graphs(
        candidate=candidate, reference_pack=None, mapping_version="dk-rdf/1.0"
    )
    assert graphs.candidate.content_hash == candidate.content_hash
    assert any(
        location == ("definitions", press.id.value)
        and node.value.startswith("https://domain-kernel.invalid/validation/")
        for node, location in graphs.locations
    )
    invalid = await model.validate(actor="editor", candidate=candidate)
    assert {issue.path for issue in invalid.issues if issue.code == "shacl_violation"} == {
        ("definitions", press.id.value, "display_name")
    }
    with pytest.raises(PublicationBlockedError):
        _ = await model.prepare_publication(actor="editor")
    reopened = await project.get_model(name=model.info.name)
    builder = DomainModelBuilder(model_info=reopened.info)
    builder.edit_concept(concept=press, display_name="Licensed press")
    repair = builder.build_change_plan(reason="Use the verified display label.")
    case = await reopened.propose_change_plan(actor="author", plan=repair)
    _ = await reopened.decide_review(
        actor="reviewer", case=case, decision=Accept(reason=repair.reason)
    )
    ready = await reopened.prepare_publication(actor="editor")
    assert not ready.validation.issues
    assert ready.validation.validator_fingerprint == invalid.validator_fingerprint
    publication = await reopened.publish(
        actor="publisher", publication=ready, version="1.0.0", reason="Deliver the reviewed shape."
    )
    archive = DomainModelBundle.deserialize(payload=publication.serialize())
    assert archive.publication.validation.semantic_fingerprints == (
        ShaclModelValidator().fingerprint,
    )
    projection = project_semantics(
        bundle=archive, base_iri=Iri(value="https://example.org/equipment/")
    )
    documents = {item.role: item.payload for item in projection.documents}
    model_shapes = documents[SemanticGraphRole.MODEL_SHAPES]
    assert b"Licensed press" in model_shapes
    shape_path = tmp_path / "instance-shapes.ttl"
    _ = shape_path.write_bytes(documents[SemanticGraphRole.INSTANCE_SHAPES])
    press_class = next(
        item.term_iri.value
        for item in projection.identities
        if item.definition.definition_id == press.id and not item.local_path
    )
    code_iri = next(
        item.term_iri.value
        for item in projection.identities
        if item.definition.definition_id == press.id
        and item.local_path == ("attributes", press.get_attribute(name="asset-code").id.value)
    )
    _ = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-I",
            "-c",
            """
import sys
from pathlib import Path
from pyshacl import validate
from rdflib import Graph, Literal, RDF, URIRef
shape_path, press_class, asset_code = sys.argv[1:]
shapes = Graph().parse(data=Path(shape_path).read_bytes(), format='turtle')
press = URIRef('https://example.org/Press-17')
records = Graph()
records.add((press, RDF.type, URIRef(press_class)))
assert validate(records, shacl_graph=shapes)[0] is False
records.add((press, URIRef(asset_code), Literal('Press-17')))
assert validate(records, shacl_graph=shapes)[0] is True
""",
            str(shape_path),
            press_class,
            code_iri,
        ],
        check=True,
        timeout=10,
        capture_output=True,
    )
    unconfigured = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(
        name="equipment"
    )
    unconfigured_model = await unconfigured.get_model(name="observed")
    with pytest.raises(PublicationBlockedError):
        _ = await unconfigured_model.prepare_publication(actor="editor")


async def test_shacl_rejects_unregistered_executable_language(tmp_path: Path) -> None:
    _, model, candidate = await _candidate(tmp_path=tmp_path, unsafe=True)
    validation = await model.validate(actor="editor", candidate=candidate)
    assert any(issue.code == "unsupported_shacl_shape" for issue in validation.issues)
