"""Exercise three independent hosts using delivered manufacturing artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from urllib.parse import unquote

from domain_kernel import (
    Accept,
    Client,
    ClientConfiguration,
    DomainModelBundle,
    JsonSchemaProjectionRequest,
    KeyEnforcementObligation,
    ModelKind,
    SemanticGraphRole,
    load_linkml,
    project_linkml,
    project_semantics,
    validate_bundle,
)
from domain_kernel.shared.hashing import hash_bytes
from examples.manufacturing_quickstart import BASE_IRI

if TYPE_CHECKING:
    from domain_kernel import Concept


async def fde(*, release: DomainModelBundle, workspace: Path) -> str:
    """Review a transferred work-order shape in a fresh host-owned workbench."""
    record = release.get_concept(name="maintenance-record")
    source_projection = project_linkml(
        bundle=release, base_iri=BASE_IRI, definition_ids=[record.id]
    )
    project = await Client(config=ClientConfiguration(base_dir=workspace)).create_project(
        name="maintenance-workbench",
        actor="demo:fde-author",
    )
    model = await project.create_model(
        actor="demo:fde-author",
        name="work-order-design",
        kind=ModelKind.PROPOSED,
        description="Review the delivered work-order vocabulary in an independent design space.",
    )
    reason = "Adopt the supplied work-order shape for local design."
    result = load_linkml(
        document=source_projection.schema,
        model_info=model.info,
        reason=reason,
        dependencies=source_projection.dependencies,
    )
    if result.plan is None:
        raise ValueError("Inspect the LinkML findings before drafting the local adoption.")
    case = await model.propose_change_plan(actor="demo:fde-author", plan=result.plan)
    decision = Accept(reason=reason)
    impact = await model.preview_changes(case=case, decision=decision)
    if impact.blockers or not impact.definition_changes:
        raise ValueError("Inspect the local work-order proposal before approving it.")
    _ = await model.decide_review(actor="demo:fde-reviewer", case=case, decision=decision)
    adopted = await model.get_concept(name=record.name)
    if adopted.id == record.id:
        raise ValueError("Local adoption must retain its own definition identity.")
    return f"FDE reviewed local {adopted.name} from release {release.version}"


def erp(*, release: DomainModelBundle, delivery: Path) -> str:
    """Configure the ERP shape using the exact transferred schema and key obligation."""
    from jsonschema import Draft202012Validator  # noqa: PLC0415 -- downstream host dependency

    schema = (delivery / "machine.schema.json").read_bytes()
    expected = (delivery / "machine.schema.sha256").read_text().strip()
    if hash_bytes(content=schema).value != expected:
        raise ValueError("Load the exact delivered machine schema bytes.")
    machine = release.get_concept(name="machine")
    key = machine.get_key(name="site-asset-identity")
    request = JsonSchemaProjectionRequest(root=machine, base_iri=BASE_IRI)
    report = release.assess_projection(request=request)
    if not any(
        isinstance(item, KeyEnforcementObligation) and item.key == key.id
        for item in report.consumer_obligations
    ):
        raise ValueError("Retain the ERP's compound asset-key obligation.")
    contract = json.loads(schema)
    root = contract["$defs"][unquote(contract["$ref"].removeprefix("#/$defs/"))]
    machine_record = {
        "@id": "https://example.org/assets/press-17",
        "@type": root["properties"]["@type"]["const"],
        "site": "Brno",
        "asset-code": "P17",
        "pressure-readings": [{"magnitude": 5, "unit": "bar"}],
    }
    validator = Draft202012Validator(contract)
    validator.validate(machine_record)
    return "ERP validated Press-17 and retained the site/asset-code key obligation"


def graphrag(*, release: DomainModelBundle) -> str:
    """Use the exact ontology and separate instance shapes for host-owned asset facts."""
    from pyshacl import validate  # noqa: PLC0415 -- optional consuming engine
    from rdflib import RDF, Graph, Literal, URIRef  # noqa: PLC0415

    machine: Concept = release.get_concept(name="machine")
    projection = project_semantics(bundle=release, base_iri=BASE_IRI)
    documents = {item.role: item for item in projection.documents}
    refs = {
        tuple(item.local_path): URIRef(item.term_iri.value)
        for item in projection.identities
        if item.definition.definition_id == machine.id
    }
    ontology = Graph().parse(data=documents[SemanticGraphRole.ONTOLOGY].payload, format="turtle")
    shapes = Graph().parse(
        data=documents[SemanticGraphRole.INSTANCE_SHAPES].payload, format="turtle"
    )
    if projection.model != release.model_version or not ontology:
        raise ValueError("Select ontology artifacts from the exact reviewed release.")
    records = Graph()
    asset = URIRef("https://example.org/assets/press-17")
    _ = records.add((asset, RDF.type, refs[()]))
    for name, value in (("site", "Brno"), ("asset-code", "P17")):
        field = machine.get_attribute(name=name)
        _ = records.add((asset, refs[("attributes", field.id.value)], Literal(value)))
    conforms, _, _ = validate(
        records,
        shacl_graph=shapes,
        inference="none",
        do_owl_imports=False,
        advanced=False,
        js=False,
    )
    if conforms is not True:
        raise ValueError("Review the example asset's facts against the delivered instance shapes.")
    return "GraphRAG validated host facts against the exact ontology and instance shapes"


def verify_deliveries(*, delivery: Path, workspace: Path) -> tuple[str, ...]:
    """Validate and consume the two transferred releases without the producer workspace."""
    first, current = (
        DomainModelBundle.deserialize(
            payload=(delivery / f"maintenance-{version}.bundle.json").read_bytes(),
        )
        for version in ("1.0.0", "1.1.0")
    )
    semantic = DomainModelBundle.deserialize(
        payload=(delivery / "maintenance-graphrag-1.0.0.bundle.json").read_bytes(),
    )
    if not all(validate_bundle(bundle=archive).valid for archive in (first, current, semantic)):
        raise ValueError("Inspect the transferred manufacturing bundles.")
    if semantic.publication.candidate.baseline != current.model_version:
        raise ValueError("Use the reviewed graph derivation of this exact manufacturing release.")
    earlier = first.get_concept(name="machine")
    updated = current.get_concept(name=earlier.name)
    if (
        earlier.id != updated.id
        or earlier.get_attribute(name="pressure-readings").max_items
        == updated.get_attribute(name="pressure-readings").max_items
    ):
        raise ValueError("Retain the original asset identity and inspect the reviewed correction.")
    return (
        asyncio.run(fde(release=current, workspace=workspace)),
        erp(release=current, delivery=delivery),
        graphrag(release=semantic),
    )


class _Options(argparse.Namespace):
    delivery: Path = Path()


def main() -> None:
    """Run the FDE, ERP and GraphRAG fixtures against delivered files."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--delivery", required=True, type=Path)
    options = parser.parse_args(namespace=_Options())
    with TemporaryDirectory(prefix="manufacturing-embeddings-") as workspace:
        for observation in verify_deliveries(delivery=options.delivery, workspace=Path(workspace)):
            _ = sys.stdout.write(observation + "\n")


if __name__ == "__main__":
    main()
