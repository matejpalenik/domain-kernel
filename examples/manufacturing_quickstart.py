"""Run the public maintenance PDFs through a reviewed manufacturing model."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from domain_kernel import (
    PDF,
    Accept,
    AcceptanceCheckDefinition,
    AttributeDefinition,
    BusinessCode,
    CheckRequirement,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    CollectionKind,
    ConceptDefinition,
    Count,
    Definition,
    DistinctDefinitionsCheck,
    DoclingParser,
    DocumentSpan,
    DomainModelBuilder,
    DomainModelBundle,
    EditDefinition,
    Iri,
    JsonSchemaProjectionRequest,
    KeyDefinition,
    LabelText,
    LanguageTag,
    LocalizedLabel,
    MeaningText,
    ModelKind,
    ModelResponse,
    ProjectionFeature,
    QuantityRequiredCheck,
    RdfProjectionRequest,
    ReaderLocation,
    RelationshipCardinality,
    RepresentationSupport,
    StructuredValueType,
    Terminology,
    ValueSetMember,
    ValueSetMembership,
)
from domain_kernel.configuration import FilesystemReader, Retention
from examples.notebooks.originals import load_manufacturing_originals

if TYPE_CHECKING:
    from domain_kernel import ContentHash, Model, ModelChangePlan, ModelRequest, Project
    from examples.notebooks.originals import ManufacturingOriginal


BASE_IRI = Iri(value="https://example.org/maintenance/")
_MAINTAINER = "demo:maintenance-reviewer"
_ASSET_CODES = ("site", "asset-code")
_PDF_PROPOSALS = {
    32: ("machine-type", "Machine type", "A physical compressor installed at a particular site."),
    1: ("work-order", "Work order", "A documented maintenance task assigned for an asset."),
}


class ManufacturingReplay:
    """Replay the authored discovery proposals with the actual selected PDF citations."""

    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Return the candidate attached to the exact single-page input."""
        (source,) = request.inputs
        (citation,) = source.evidence
        if not isinstance(citation.locator, DocumentSpan) or citation.locator.page is None:
            raise ValueError("Select the verified maintenance page.")
        name, label, meaning = _PDF_PROPOSALS[citation.locator.page]
        return ModelResponse(
            model_id="replay/manufacturing-maintenance",
            output_json=json.dumps(
                {
                    "concepts": [
                        {
                            "name": name,
                            "display_name": label,
                            "meaning": meaning,
                            "citations": [1],
                            "confidence": None,
                        }
                    ],
                    "relationships": [],
                },
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ManufacturingDelivery:
    """The exact two releases and the current ERP shape delivery."""

    first: DomainModelBundle
    current: DomainModelBundle
    semantic: DomainModelBundle
    schema: bytes
    schema_hash: ContentHash
    exact_history: bool


async def _review_discovery(
    *, project: Project, model: Model, originals: tuple[ManufacturingOriginal, ...]
) -> None:
    for selected in originals:
        captured = await project.ingest_source(
            actor="demo:maintenance-author",
            name=selected.identifier,
            source=PDF(
                location=ReaderLocation(reader="manuals", path=selected.relative_path),
                pages=[selected.page],
                expected_hash=selected.digest,
            ),
        )
        draft = await model.extract_proposals(
            actor="demo:maintenance-author",
            source_revisions=[captured.revision],
            additional_instructions="Distinguish equipment specifications from plant records.",
        )
        alignment = await model.propose_alignment(
            actor="demo:maintenance-author", discovery_id=draft.id
        )
        (case,) = (await model.list_review_cases(reconciliation_id=alignment.id)).items
        (proposal,) = case.definitions
        (citation,) = case.evidence
        content = await project.get_evidence(evidence=citation)
        if (
            citation.source.revision_id != captured.revision_id
            or not isinstance(citation.locator, DocumentSpan)
            or citation.locator.page != selected.page
            or not content.excerpt
        ):
            raise ValueError("Review the exact evidence from the selected publisher page.")
        decision = (
            EditDefinition(
                definition_id=proposal.id,
                name=proposal.name,
                display_name=proposal.display_name,
                meaning="The manufacturer's product model for compressor specifications.",
                body=ConceptDefinition(),
                reason="The instruction book describes a product type across installations.",
            )
            if proposal.name == "machine-type"
            else Accept(reason="Keep the documented maintenance task as a separate concept.")
        )
        _ = await model.preview_changes(case=case, decision=decision)
        _ = await model.decide_review(actor=_MAINTAINER, case=case, decision=decision)


async def _review(*, model: Model, plan: ModelChangePlan) -> None:
    case = await model.propose_change_plan(actor="demo:maintenance-author", plan=plan)
    decision = Accept(reason=plan.reason)
    impact = await model.preview_changes(case=case, decision=decision)
    if impact.blockers:
        raise ValueError("Repair the inspected manufacturing changes before review.")
    _ = await model.decide_review(actor=_MAINTAINER, case=case, decision=decision)


def _local_vocabulary(*, code: str, name: str, description: str) -> ValueSetMember:
    return ValueSetMember(
        code=BusinessCode(value=code),
        label=LabelText(value=name),
        meaning=MeaningText(value=description),
    )


def _build_contract(
    *, model: Model, machine_type: Definition, work_order: Definition
) -> ModelChangePlan:
    builder = DomainModelBuilder(model_info=model.info)
    bar = builder.add_unit(name="bar", symbol="bar", meaning="A local unit for reported pressure.")
    units = builder.add_value_set(
        name="pressure-units",
        meaning="Pressure units used by the application.",
        membership=ValueSetMembership.CLOSED,
        members=[
            ValueSetMember(
                code=BusinessCode(value="bar"),
                label=LabelText(value="Bar"),
                meaning=MeaningText(value="Report the pressure in bar."),
                unit=bar,
            )
        ],
    )
    pressure = builder.add_quantity(
        name="pressure", meaning="Reported pressure reading.", units=units
    )
    statuses = builder.add_value_set(
        name="maintenance-status",
        meaning="States used by the local maintenance application.",
        membership=ValueSetMembership.CLOSED,
        members=[
            _local_vocabulary(
                code="queued", name="Queued", description="The task is awaiting work."
            ),
            _local_vocabulary(
                code="complete", name="Complete", description="The work is recorded."
            ),
        ],
    )
    site, code = (AttributeDefinition.string(name=name, required=True) for name in _ASSET_CODES)
    machine = builder.add_concept(
        name="machine",
        meaning="An individual physical production asset at a plant.",
        attributes=[
            site,
            code,
            AttributeDefinition(
                name="pressure-readings",
                value_type=StructuredValueType(structure=pressure),
                collection=CollectionKind.SET,
                max_items=Count(value=4),
            ),
        ],
        keys=[KeyDefinition(name="site-asset-identity", attributes=[site.id, code.id])],
        terminology=Terminology(
            labels=[
                LocalizedLabel(language=LanguageTag(value="en"), text=LabelText(value="Machine")),
                LocalizedLabel(language=LanguageTag(value="cs"), text=LabelText(value="Stroj")),
            ]
        ),
    )
    _ = builder.add_concept(
        name="maintenance-record",
        meaning="The local application record for the status of a reviewed work order.",
        attributes=[
            AttributeDefinition.value_set(
                name="maintenance-status", value_set=statuses, required=True
            ),
        ],
    )
    _ = builder.add_relationship(
        name="work-order-concerns-machine",
        meaning="The order records work for one asset.",
        source=work_order,
        target=machine,
        cardinality=RelationshipCardinality.many_to_one(),
    )
    _ = builder.add_relationship(
        name="machine-has-product-type",
        meaning="The installed asset uses the reviewed product specification.",
        source=machine,
        target=machine_type,
        cardinality=RelationshipCardinality.many_to_one(),
    )
    for name, predicate in (
        ("separate-asset-and-type", DistinctDefinitionsCheck(left=machine, right=machine_type.id)),
        ("pressure-unit-present", QuantityRequiredCheck(structure=pressure)),
    ):
        _ = builder.add_definition(
            name=name,
            meaning="Verify the reviewed manufacturing contract before release.",
            body=AcceptanceCheckDefinition(
                statement=MeaningText(value="Check the exact reviewed definition references."),
                requirement=CheckRequirement.REQUIRED,
                predicate=predicate,
            ),
            referenced_definitions=[machine_type],
        )
    return builder.build_change_plan(
        reason="Approve the application-authored fields and exact references."
    )


async def _publish(*, model: Model, version: str, reason: str) -> DomainModelBundle:
    preparation = await model.prepare_publication(actor=_MAINTAINER)
    return await model.publish(
        publication=preparation,
        version=version,
        actor="demo:maintenance-publisher",
        reason=reason,
    )


async def _graph_contract(*, project: Project, release: DomainModelBundle) -> DomainModelBundle:
    request = RdfProjectionRequest(base_iri=BASE_IRI)
    assessment = release.assess_projection(request=request)
    if assessment.exportable or not any(
        item.feature is ProjectionFeature.VALUE_EQUALITY
        and item.representation is RepresentationSupport.UNSUPPORTED
        for item in assessment.findings
    ):
        raise ValueError("Inspect the unsupported structured-set equality before deriving a graph.")
    graph_model = await project.create_model(
        actor="demo:maintenance-author",
        name="compressor-asset-graph",
        kind=ModelKind.PROPOSED,
        description="Review the asset identities and relationships for graph consumption.",
        copy_from=release,
    )
    machine = await graph_model.get_concept(name="machine")
    builder = DomainModelBuilder(model_info=graph_model.info)
    builder.remove_attribute(
        concept=machine, attribute=machine.get_attribute(name="pressure-readings")
    )
    await _review(
        model=graph_model,
        plan=builder.build_change_plan(
            reason="Select identity and relationship facts for GraphRAG."
        ),
    )
    projected = await _publish(
        model=graph_model, version="1.0.0", reason="Deliver the reviewed graph-specific derivation."
    )
    if not projected.assess_projection(request=request).exportable:
        raise ValueError("Inspect the reviewed graph projection before handing it to GraphRAG.")
    return projected


async def run_manufacturing(*, originals: Path, workspace: Path) -> ManufacturingDelivery:
    """Parse pinned pages, review the manufacturing contract and reopen both releases."""
    selected = load_manufacturing_originals(directory=originals)
    config = ClientConfiguration(
        base_dir=workspace,
        readers=[FilesystemReader(name="manuals", root=originals)],
        retention=Retention(extracted_text=True),
        model_gateway=ManufacturingReplay(),
    )
    project = await Client(
        config=config,
        integrations=ClientIntegrations(format_parsers={"pdf": DoclingParser()}),
    ).create_project(name="maintenance", actor="demo:maintenance-author")
    model = await project.create_model(
        name="compressor-maintenance",
        kind=ModelKind.PROPOSED,
        actor="demo:maintenance-author",
        description="Review asset identities and maintenance data for compressed air equipment.",
    )
    await _review_discovery(project=project, model=model, originals=selected)
    model = await project.get_model(name=model.info.name)
    machine_type = await model.get_concept(name="machine-type")
    work_order = await model.get_concept(name="work-order")
    await _review(
        model=model,
        plan=_build_contract(model=model, machine_type=machine_type, work_order=work_order),
    )
    first = await _publish(
        model=model, version="1.0.0", reason="Release the reviewed maintenance contract."
    )

    model = await project.get_model(name=model.info.name)
    machine = await model.get_concept(name="machine")
    builder = DomainModelBuilder(model_info=model.info)
    builder.edit_attribute(
        concept=machine,
        attribute=machine.get_attribute(name="pressure-readings"),
        max_items=Count(value=5),
    )
    await _review(
        model=model,
        plan=builder.build_change_plan(
            reason="Allow five reviewed readings per application record."
        ),
    )
    current = await _publish(
        model=model, version="1.1.0", reason="Release the reviewed collection correction."
    )

    detached_project = await Client(config=ClientConfiguration(base_dir=workspace)).get_project(
        name=project.name
    )
    reopened = await detached_project.get_model(name=model.info.name)
    exact_history = (
        await reopened.get_version(version=first.version) == first
        and await reopened.get_version(version=current.version) == current
    )
    if not exact_history:
        raise ValueError("Reopen the exact two maintenance releases before delivery.")
    request = JsonSchemaProjectionRequest(
        root=current.get_concept(name="machine"), base_iri=BASE_IRI
    )
    report = current.assess_projection(request=request)
    if not report.exportable:
        raise ValueError("Inspect the maintenance projection findings before export.")
    artifact = await reopened.export(
        actor="demo:maintenance-publisher",
        bundle=current,
        request=request,
        store="artifacts",
        path="machine.schema.json",
    )
    if report.consumer_obligations != artifact.consumer_obligations:
        raise ValueError("Preserve the inspected consumer obligations in the delivered schema.")
    schema = (workspace / ".domain-kernel/artifacts" / artifact.key).read_bytes()
    return ManufacturingDelivery(
        first=first,
        current=current,
        semantic=await _graph_contract(project=project, release=current),
        schema=schema,
        schema_hash=artifact.content_hash,
        exact_history=exact_history,
    )


def write_manufacturing_delivery(*, result: ManufacturingDelivery, output: Path) -> None:
    """Deliver the reviewed archives and exact ERP schema as independent files."""
    output.mkdir(parents=True, exist_ok=True)
    for archive in (result.first, result.current):
        _ = (output / f"maintenance-{archive.version}.bundle.json").write_bytes(archive.serialize())
    _ = (output / "maintenance-graphrag-1.0.0.bundle.json").write_bytes(result.semantic.serialize())
    _ = (output / "machine.schema.json").write_bytes(result.schema)
    _ = (output / "machine.schema.sha256").write_text(result.schema_hash.value + "\n")


class _Options(argparse.Namespace):
    originals: Path = Path()
    output: Path = Path()


def main() -> None:
    """Run the maintenance journey and transfer the exact reviewed contracts."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--originals", required=True, type=Path)
    _ = parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args(namespace=_Options())
    with TemporaryDirectory(prefix="manufacturing-producer-") as workspace:
        result = asyncio.run(
            run_manufacturing(originals=options.originals, workspace=Path(workspace))
        )
    write_manufacturing_delivery(result=result, output=options.output)
    _ = sys.stdout.write("Published and reopened manufacturing contracts 1.0.0 and 1.1.0\n")


if __name__ == "__main__":
    main()
