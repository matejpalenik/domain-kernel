"""Check portable business records with an independent JSON Schema validator."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AttributeDefinition,
    Client,
    ClientConfiguration,
    CollectionKind,
    Count,
    DecimalFacets,
    DecimalPrecision,
    DecimalScale,
    DefinitionId,
    DefinitionKindMismatchError,
    DefinitionNotFoundError,
    DomainModelBuilder,
    Iri,
    JsonSchemaProjectionRequest,
    KeyDefinition,
    LinkmlProjectionRequest,
    MappingId,
    ModelKind,
    Nullability,
    PinnedDefinitionReference,
    ProjectionAvailability,
    ProjectionBlockedError,
    ProjectionFeature,
    RelationshipCardinality,
    ScopeMismatchError,
    SemanticGraphRole,
    StaleStateError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import DomainModelBundle, Model

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
_BASE = Iri(value="https://example.org/recruitment/")


async def _release(*, path: Path) -> tuple[Model, DomainModelBundle, DefinitionId]:
    project = await Client(config=ClientConfiguration(base_dir=path)).create_project(
        actor="editor", name="recruitment"
    )
    model = await project.create_model(
        actor="editor", name="observed", kind=ModelKind.OBSERVED, description="Recruitment review."
    )
    builder = DomainModelBuilder(model_info=model.info)
    identifier = AttributeDefinition.string(name="identifier", required=True)
    fields = [
        AttributeDefinition.string(
            name=f"{presence}-{minimum}",
            required=presence == "required",
            collection=CollectionKind.SET,
            min_items=Count(value=minimum),
            max_items=Count(value=1),
        )
        for presence in ("required", "optional")
        for minimum in (0, 1)
    ]
    candidate = builder.add_concept(
        name="applicant",
        meaning="An applicant for recruitment.",
        attributes=[
            identifier,
            *fields,
            AttributeDefinition.string(name="note", nullability=Nullability.ALLOWED),
        ],
        keys=[KeyDefinition(name="lookup", attributes=[identifier.id])],
    )
    _ = builder.add_concept(
        name="salary",
        meaning="A bounded salary.",
        attributes=[
            AttributeDefinition.decimal(
                name="amount",
                facets=DecimalFacets(
                    precision=DecimalPrecision(value=4), scale=DecimalScale(value=2)
                ),
            )
        ],
    )
    relation = builder.add_relationship(
        name="refers",
        meaning="An applicant refers another applicant.",
        source=candidate,
        target=candidate,
        cardinality=RelationshipCardinality.many_to_many(),
    )
    plan = builder.build_change_plan(reason="Approve the published shape.")
    case = await model.propose_change_plan(actor="editor", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    prepared = await model.prepare_publication(actor="editor")
    release = await model.publish(
        actor="publisher", publication=prepared, version="1.0.0", reason="Deliver the contract."
    )
    return model, release, relation


async def test_schema_presence_bounds_and_normalized_delivery(tmp_path: Path) -> None:
    model, bundle, _ = await _release(path=tmp_path)
    applicant = bundle.get_concept(name="applicant")
    inputs = [
        JsonSchemaProjectionRequest(root=applicant, base_iri=_BASE),
        JsonSchemaProjectionRequest(root=applicant.id, base_iri=_BASE),
        JsonSchemaProjectionRequest(
            root=PinnedDefinitionReference(
                model=bundle.model_version,
                definition_id=applicant.id,
                definition_revision=applicant.revision,
            ),
            base_iri=_BASE,
        ),
    ]
    reports = [bundle.assess_projection(request=request) for request in inputs]
    assert all(report.exportable and report == reports[0] for report in reports)
    results = [
        await model.export(
            actor="publisher",
            bundle=bundle,
            store="artifacts",
            path="applicant.schema.json",
            request=request,
            idempotency_key="schema-delivery",
        )
        for request in inputs
    ]
    assert all(artifact == results[0] for artifact in results)
    assert results[0].consumer_obligations == reports[0].consumer_obligations
    assert results[0].schema is not None
    assert results[0].schema.root == inputs[-1].root
    path = tmp_path / ".domain-kernel/artifacts" / results[0].key
    _ = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-I",
            "-c",
            """
import json
import sys
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
schema = json.loads(Path(sys.argv[1]).read_bytes())
Draft202012Validator.check_schema(schema)
contract = Draft202012Validator(schema, format_checker=FormatChecker())
by_ref = schema['$defs'][schema['$ref'].removeprefix('#/$defs/')]
def example(**values):
    base = {'@id': 'https://example.org/applicants/1',
            '@type': by_ref['properties']['@type']['const'],
            'identifier': 'app-1', 'required-0': [], 'required-1': ['one']}
    return base | values
assert contract.is_valid(example())
assert contract.is_valid(example(note=None))
for field, minimum, required in (
    ('required-0', 0, True), ('required-1', 1, True),
    ('optional-0', 0, False), ('optional-1', 1, False),
):
    skipped = example()
    skipped.pop(field, None)
    assert contract.is_valid(skipped) is not required
    assert contract.is_valid(example(**{field: []})) is (minimum == 0)
    assert not contract.is_valid(example(**{field: None}))
    assert contract.is_valid(example(**{field: ['one']}))
    assert not contract.is_valid(example(**{field: ['one','two']}))
assert not contract.is_valid(example(**{'@id': 'relative'}))
assert 'minItems' not in by_ref['properties']['note']
relationship = next(name for name in by_ref['properties'] if name.startswith('rel:'))
peer = {'@id': 'https://example.org/applicants/2',
        '@type': by_ref['properties']['@type']['const']}
assert contract.is_valid(example(**{relationship: [peer]}))
assert not contract.is_valid(example(**{relationship: [peer | {'display': 'Extra'}]}))
""",
            str(path),
        ],
        check=True,
        timeout=10,
        capture_output=True,
    )


async def test_invalid_roots_and_unsupported_projection_preserve_bundle(tmp_path: Path) -> None:
    model, bundle, relation = await _release(path=tmp_path)
    _, foreign, _ = await _release(path=tmp_path / "second")
    applicant = bundle.get_concept(name="applicant")
    for root, error in (
        (foreign.get_concept(name="applicant"), ScopeMismatchError),
        (DefinitionId(value="missing"), DefinitionNotFoundError),
        (relation, DefinitionKindMismatchError),
        (replace(applicant, display_name="Substituted label"), StaleStateError),
    ):
        with pytest.raises(error):
            _ = bundle.assess_projection(
                request=JsonSchemaProjectionRequest(root=root, base_iri=_BASE)
            )
    request = JsonSchemaProjectionRequest(root=bundle.get_concept(name="salary"), base_iri=_BASE)
    report = bundle.assess_projection(request=request)
    assert not report.exportable
    assert any(finding.feature is ProjectionFeature.DECIMAL_FACETS for finding in report.findings)
    with pytest.raises(ProjectionBlockedError) as failure:
        _ = await model.export(
            actor="publisher",
            bundle=bundle,
            store="artifacts",
            path="salary.schema.json",
            request=request,
        )
    assert failure.value.assessment == report
    with pytest.raises(TypeError, match="only for an RDF"):
        _ = await model.export(
            actor="publisher",
            bundle=bundle,
            store="artifacts",
            path="wrong-role.json",
            request=request,
            role=SemanticGraphRole.ONTOLOGY,
        )
    assert not (tmp_path / ".domain-kernel/artifacts").exists()
    assert type(bundle).deserialize(payload=bundle.serialize()) == bundle


async def test_exact_dependency_root_and_unavailable_mapping(tmp_path: Path) -> None:
    _, dependency, _ = await _release(path=tmp_path)
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(
        name="recruitment"
    )
    model = await project.create_model(
        actor="editor",
        name="local",
        kind=ModelKind.PROPOSED,
        description="Reuse the reviewed shape.",
        dependencies=[dependency.model_version],
    )
    concept = dependency.get_concept(name="applicant")
    pin = PinnedDefinitionReference(
        model=dependency.model_version,
        definition_id=concept.id,
        definition_revision=concept.revision,
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_concept(
        name="interview-record",
        meaning="An interview with one applicant.",
        attributes=[AttributeDefinition.reference(name="applicant", target=pin, required=True)],
    )
    plan = builder.build_change_plan(reason="Review the exact applicant reference.")
    case = await model.propose_change_plan(actor="editor", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    prepared = await model.prepare_publication(actor="editor")
    bundle = await model.publish(
        actor="publisher", publication=prepared, version="1.0.0", reason="Deliver the exact reuse."
    )
    report = bundle.assess_projection(request=JsonSchemaProjectionRequest(root=pin, base_iri=_BASE))
    assert report.exportable
    assert isinstance(report.request, JsonSchemaProjectionRequest)
    assert report.request.root == pin
    assert all(
        item.location.definition.model == dependency.model_version for item in report.findings
    )
    with pytest.raises(StaleStateError):
        _ = bundle.assess_projection(
            request=JsonSchemaProjectionRequest(
                root=replace(pin, definition_revision=pin.definition_revision + 1),
                base_iri=_BASE,
            )
        )
    request = LinkmlProjectionRequest(base_iri=_BASE, mapping=MappingId(value="unsupported/1.0"))
    unsupported = bundle.assess_projection(request=request)
    assert unsupported.availability is ProjectionAvailability.UNSUPPORTED_MAPPING
    assert not unsupported.findings
    assert not (tmp_path / ".domain-kernel/artifacts").exists()
