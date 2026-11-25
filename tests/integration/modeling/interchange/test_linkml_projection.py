"""Exercise LinkML on published source profiles and portable schema bytes."""

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
    BusinessCode,
    CardinalityBounds,
    Client,
    ClientConfiguration,
    CollectionKind,
    CollectionSemanticsObligation,
    ConceptDefinition,
    Count,
    CreateDefinition,
    DataType,
    DomainModelBuilder,
    InvalidSchemaError,
    Iri,
    LabelText,
    LinkmlProjectionRequest,
    LinkmlSyntax,
    MeaningText,
    ModelKind,
    RelationshipCardinality,
    RelationshipDefinition,
    ScalarValueType,
    SchemaDocument,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
    ValueSetMember,
    ValueSetMembership,
    load_linkml,
    project_linkml,
)
from domain_kernel.modeling.domain.portable_json import read_portable_object
from domain_kernel.shared.hashing import canonical_json_bytes, hash_bytes

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import DomainModelBundle, Project
    from domain_kernel.shared.hashing import JsonValue

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
pytest.importorskip("linkml_runtime")
_BASE = Iri(value="https://example.org/contracts/")


async def _release(*, path: Path) -> tuple[Project, DomainModelBundle]:
    project = await Client(config=ClientConfiguration(base_dir=path)).create_project(
        actor="editor", name="interchange"
    )
    model = await project.create_model(
        actor="editor",
        name="recruitment",
        kind=ModelKind.OBSERVED,
        description="Recruitment shapes.",
    )
    builder = DomainModelBuilder(model_info=model.info)
    hour = builder.add_unit(name="hour", symbol="h", meaning="A local processing unit.")
    units = builder.add_value_set(
        name="duration-unit",
        meaning="Permitted unit codes.",
        membership=ValueSetMembership.CLOSED,
        members=[
            ValueSetMember(
                code=BusinessCode(value="h"),
                label=LabelText(value="Hour"),
                meaning=MeaningText(value="Elapsed hour."),
                unit=hour,
            )
        ],
    )
    _ = builder.add_quantity(name="duration", meaning="Elapsed processing duration.", units=units)
    stages = builder.add_value_set(
        name="stage-codes",
        meaning="Known recruitment stages.",
        membership=ValueSetMembership.OPEN,
        members=[
            ValueSetMember(
                code=BusinessCode(value="screen"),
                label=LabelText(value="Screen"),
                meaning=MeaningText(value="Screening applications."),
            )
        ],
    )
    first = builder.add_concept(
        name="screening",
        meaning="An application screening workflow.",
        attributes=[
            AttributeDefinition.value_set(
                name="stages",
                value_set=stages,
                required=True,
                collection=CollectionKind.SET,
                min_items=Count(value=0),
                max_items=Count(value=2),
            ),
            AttributeDefinition.string(
                name="tags",
                collection=CollectionKind.SET,
                min_items=Count(value=1),
                max_items=Count(value=3),
            ),
        ],
    )
    second = builder.add_concept(name="applicant", meaning="A person who applies.")
    _ = builder.add_relationship(
        name="screens",
        meaning="A workflow screens applications from applicants.",
        source=first,
        target=second,
        cardinality=RelationshipCardinality(
            outgoing=CardinalityBounds(minimum=Count(value=1), maximum=Count(value=3)),
            incoming=CardinalityBounds(minimum=Count(value=0), maximum=Count(value=2)),
        ),
    )
    plan = builder.build_change_plan(reason="Review the exact recruitment contract.")
    case = await model.propose_change_plan(actor="editor", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    prepared = await model.prepare_publication(actor="editor")
    bundle = await model.publish(
        actor="publisher",
        publication=prepared,
        version="1.0.0",
        reason="Share the approved schema.",
    )
    return project, bundle


async def test_linkml_roundtrip_keeps_bounds_units_and_fresh_ids(tmp_path: Path) -> None:
    project, bundle = await _release(path=tmp_path)
    projected = project_linkml(bundle=bundle, base_iri=_BASE, syntax=LinkmlSyntax.JSON)
    report = bundle.assess_projection(
        request=LinkmlProjectionRequest(base_iri=_BASE, syntax=LinkmlSyntax.JSON)
    )
    assert report.exportable
    assert projected.consumer_obligations == report.consumer_obligations
    assert {
        item.attribute
        for item in report.consumer_obligations
        if isinstance(item, CollectionSemanticsObligation)
    } == {field.id for field in bundle.get_concept(name="screening").attributes}

    target = await project.create_model(
        actor="author",
        name="import",
        kind=ModelKind.PROPOSED,
        description="Review a received recipe.",
    )
    result = load_linkml(
        document=projected.schema,
        dependencies=projected.dependencies,
        model_info=target.info,
        reason="Review the transferred recruitment schema.",
    )
    assert result.plan is not None, result.issues
    assert not (await target.list_definitions()).items
    assert len(result.origins) == len(projected.selected) + 1
    assert not {
        item.definition_id for item in result.plan.operations if isinstance(item, CreateDefinition)
    } & {pin.definition_id for pin in projected.selected}
    review = await target.propose_change_plan(actor="author", plan=result.plan)
    _ = await target.decide_review(
        actor="reviewer",
        case=review,
        decision=Accept(reason="Use the independently supplied shapes."),
    )
    by_name = {item.name: item for item in (await target.list_definitions()).items}
    screening = await target.get_concept(name="screening")
    required = screening.get_attribute(name="stages")
    optional = screening.get_attribute(name="tags")
    assert (required.required, required.min_items, required.max_items) == (
        True,
        Count(value=0),
        Count(value=2),
    )
    assert (optional.required, optional.min_items, optional.max_items) == (
        False,
        Count(value=1),
        Count(value=3),
    )
    assert required.id != bundle.get_concept(name="screening").get_attribute(name="stages").id
    assert isinstance(by_name["stage-codes"].body, ValueSetDefinition)
    assert by_name["stage-codes"].body.membership is ValueSetMembership.OPEN
    assert isinstance(by_name["hour"].body, UnitDefinition)
    vocabulary = by_name["duration-unit"].body
    assert isinstance(vocabulary, ValueSetDefinition)
    assert vocabulary.members[0].unit == by_name["hour"].id
    quantity = by_name["duration"].body
    assert isinstance(quantity, StructuredValueDefinition)
    assert quantity.quantity is not None
    assert quantity.quantity.quantity_kind is None
    relation = by_name["screens"].body
    assert isinstance(relation, RelationshipDefinition)
    assert relation.source_concept_id == screening.id
    assert relation.target_concept_id == by_name["applicant"].id
    assert relation.cardinality.outgoing.maximum == Count(value=3)
    assert relation.cardinality.incoming.maximum == Count(value=2)
    assert screening.schema_origins
    previous = await (await project.get_model(name="recruitment")).get_version(
        version=bundle.version
    )
    assert previous == bundle


async def test_linkml_refuses_tightened_open_vocabulary(tmp_path: Path) -> None:
    project, bundle = await _release(path=tmp_path)
    projected = project_linkml(bundle=bundle, base_iri=_BASE, syntax=LinkmlSyntax.JSON)
    schema = read_portable_object(
        payload=projected.schema.payload,
        expected_hash=projected.schema.content_hash,
        resource="schema",
        max_bytes=1024 * 1024,
    )
    types = schema["types"]
    assert isinstance(types, dict)
    stages = types["stage-codes"]
    assert isinstance(stages, dict)
    stages["pattern"] = "screen"
    payload = canonical_json_bytes(value=schema)
    damaged: SchemaDocument = replace(
        projected.schema, payload=payload, content_hash=hash_bytes(content=payload)
    )
    target = await project.create_model(
        actor="author",
        name="import",
        kind=ModelKind.PROPOSED,
        description="Review a received schema.",
    )
    result = load_linkml(
        document=damaged,
        dependencies=projected.dependencies,
        model_info=target.info,
        reason="Inspect the supplied vocabulary.",
    )
    assert result.plan is None
    assert result.issues
    with pytest.raises(InvalidSchemaError):
        _ = load_linkml(
            document=replace(projected.schema, payload=payload),
            model_info=target.info,
            reason="Check the schema transport signature.",
        )


async def test_linkml_resolves_only_exact_supplied_imports(tmp_path: Path) -> None:
    project, _ = await _release(path=tmp_path)
    target = await project.create_model(
        actor="author",
        name="dependency-import",
        kind=ModelKind.PROPOSED,
        description="Import only the supplied declarations.",
    )
    root_iri = Iri(value="https://example.org/contracts/root")
    dependency_iri = Iri(value="https://example.org/contracts/shared")
    root = _schema(
        iri=root_iri,
        raw={
            "id": "c:root",
            "prefixes": {"c": _BASE.value, "terms": "https://example.org/terms/"},
            "imports": ["c:shared", "linkml:types"],
            "classes": {
                "assessment": {
                    "description": "A reviewed candidate assessment.",
                    "attributes": {"candidate": {"range": "terms:applicant", "required": True}},
                },
            },
        },
    )
    shared_fields: dict[str, JsonValue] = {
        "id": dependency_iri.value,
        "prefixes": {"terms": "https://example.org/terms/"},
        "classes": {
            "applicant": {"class_uri": "terms:applicant", "description": "An applicant."},
        },
    }
    shared = _schema(iri=dependency_iri, raw=shared_fields)
    result = load_linkml(
        document=root, dependencies=[shared], model_info=target.info, reason="Review exact imports."
    )
    assert result.plan is not None
    assert {item.schema_iri for item in result.origins} == {root_iri, dependency_iri}
    assert any(shared.content_hash in item.dependency_hashes for item in result.origins)
    with pytest.raises(InvalidSchemaError) as absent:
        _ = load_linkml(document=root, model_info=target.info, reason="Require the pinned import.")
    assert absent.value.issues[0].code == "schema_import_missing"
    cycle = _schema(iri=dependency_iri, raw={**shared_fields, "imports": [root_iri.value]})
    with pytest.raises(InvalidSchemaError) as cyclic:
        _ = load_linkml(
            document=root, dependencies=[cycle], model_info=target.info, reason="Reject a cycle."
        )
    assert cyclic.value.issues[0].code == "schema_import_cycle"
    conflict = _schema(
        iri=dependency_iri,
        raw={**shared_fields, "prefixes": {"terms": "https://example.org/different/"}},
    )
    with pytest.raises(InvalidSchemaError) as conflicting:
        _ = load_linkml(
            document=root,
            dependencies=[conflict],
            model_info=target.info,
            reason="Reject conflicting prefixes.",
        )
    assert conflicting.value.issues[0].code == "schema_prefix_conflict"
    assert not (await target.list_definitions()).items


@pytest.mark.parametrize("order", [("left", "right"), ("right", "left")])
async def test_linkml_import_order_does_not_resolve_conflicting_meanings(
    tmp_path: Path, *, order: tuple[str, str]
) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author", name="interchange"
    )
    model = await project.create_model(
        actor="author",
        name="dependent-schema",
        kind=ModelKind.PROPOSED,
        description="Review a schema formed from two exact dependencies.",
    )
    root_iri = Iri(value=f"{_BASE.value}root")
    root = _schema(
        iri=root_iri,
        raw={"id": root_iri.value, "imports": [f"{_BASE.value}{name}" for name in order]},
    )
    dependencies = [
        _schema(
            iri=Iri(value=f"{_BASE.value}{name}"),
            raw={
                "id": f"{_BASE.value}{name}",
                "classes": {
                    "applicant": {
                        "class_uri": "https://example.org/terms/Applicant",
                        "description": description,
                    }
                },
            },
        )
        for name, description in (
            ("left", "A person applying for a role."),
            ("right", "An organization applying for a contract."),
        )
    ]
    with pytest.raises(InvalidSchemaError) as caught:
        _ = load_linkml(
            document=root,
            dependencies=dependencies,
            model_info=model.info,
            reason="Do not choose a meaning based on import order.",
        )
    assert caught.value.issues[0].code == "schema_declaration_conflict"
    assert not (await model.list_definitions()).items
    assert not (await model.list_review_cases()).items


async def test_native_linkml_keeps_open_presence_and_permissible_meanings(tmp_path: Path) -> None:
    project, bundle = await _release(path=tmp_path)
    projection = project_linkml(bundle=bundle, base_iri=_BASE)
    schema_path = tmp_path / "duration.linkml.yaml"
    _ = schema_path.write_bytes(projection.schema.payload)
    loaded = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-I",
            "-c",
            """
import sys
from pathlib import Path
from linkml_runtime.linkml_model import SchemaDefinition
from linkml_runtime.loaders import yaml_loader
source = Path(sys.argv[1]).read_text()
schema = yaml_loader.loads(source, target_class=SchemaDefinition)
assert schema.types["stage-codes"].typeof == "string"
assert schema.types["stage-codes"].pattern is None
stage = schema.classes["screening"].attributes["stages"]
assert stage.range == "stage-codes" and stage.required is True and stage.multivalued is True
assert stage.minimum_cardinality == 0 and stage.maximum_cardinality == 2
optional = schema.classes["screening"].attributes["tags"]
assert optional.required is False and optional.minimum_cardinality == 1
codes = schema.enums["duration-unit"].permissible_values
assert set(codes) == {"h"}
assert codes["h"].meaning.startswith("https://example.org/contracts/projects/")
""",
            str(schema_path),
        ],
        check=False,
        timeout=15,
        capture_output=True,
    )
    assert loaded.returncode == 0, loaded.stderr
    recipient = await project.create_model(
        actor="editor",
        name="receiving",
        kind=ModelKind.PROPOSED,
        description="Inspect the supplied business shapes.",
    )
    good = load_linkml(
        document=projection.schema, model_info=recipient.info, reason="Import the exact YAML."
    )
    assert good.plan is not None, good.issues
    invalid_text = b"id: https://example.org/duplicate\nclasses: {}\nclasses: {}\n"
    invalid = SchemaDocument(
        schema_iri=Iri(value="https://example.org/duplicate"),
        syntax=LinkmlSyntax.YAML,
        payload=invalid_text,
        content_hash=hash_bytes(content=invalid_text),
    )
    with pytest.raises(InvalidSchemaError):
        _ = load_linkml(document=invalid, model_info=recipient.info, reason="Check duplicate keys.")


def _schema(*, iri: Iri, raw: dict[str, JsonValue]) -> SchemaDocument:
    payload = canonical_json_bytes(value=raw)
    return SchemaDocument(
        schema_iri=iri,
        syntax=LinkmlSyntax.JSON,
        payload=payload,
        content_hash=hash_bytes(content=payload),
    )


async def test_linkml_rejects_enum_drift_and_preserves_plain_string_fallback(
    tmp_path: Path,
) -> None:
    project, bundle = await _release(path=tmp_path)
    projection = project_linkml(bundle=bundle, base_iri=_BASE, syntax=LinkmlSyntax.JSON)
    raw = read_portable_object(
        payload=projection.schema.payload,
        expected_hash=projection.schema.content_hash,
        resource="schema",
        max_bytes=1024 * 1024,
    )
    classes = raw["classes"]
    assert isinstance(classes, dict)
    screening = classes["screening"]
    assert isinstance(screening, dict)
    fields = screening["attributes"]
    assert isinstance(fields, dict)
    tags = fields["tags"]
    assert isinstance(tags, dict)
    del tags["required"]

    types = raw["types"]
    assert isinstance(types, dict)
    stage = types["stage-codes"]
    assert isinstance(stage, dict)
    annotations = stage["annotations"]
    assert isinstance(annotations, dict)
    del annotations["dk:open_value_set"]

    workspace = await project.create_model(
        actor="editor",
        name="fallback",
        kind=ModelKind.PROPOSED,
        description="Review a form without a supplied vocabulary annotation.",
    )
    good = load_linkml(
        document=_schema(iri=projection.schema.schema_iri, raw=raw),
        model_info=workspace.info,
        reason="Review the permissive form.",
    )
    assert good.plan is not None, good.issues
    proposals = {
        op.content.name: op.content.body
        for op in good.plan.operations
        if isinstance(op, CreateDefinition)
    }
    assert "stage-codes" not in proposals
    body = proposals["screening"]
    assert isinstance(body, ConceptDefinition)
    imported = {field.name: field for field in body.attributes}
    assert imported["stages"].value_type == ScalarValueType(data_type=DataType.STRING)
    assert imported["tags"].required is False
    assert imported["tags"].min_items == Count(value=1)

    enums = raw["enums"]
    assert isinstance(enums, dict)
    duration = enums["duration-unit"]
    assert isinstance(duration, dict)
    values = duration["permissible_values"]
    assert isinstance(values, dict)
    hour = values["h"]
    assert isinstance(hour, dict)
    hour["meaning"] = "https://example.org/unrelated-unit"
    blocked = load_linkml(
        document=_schema(iri=projection.schema.schema_iri, raw=raw),
        model_info=workspace.info,
        reason="Reject changed reusable-unit meaning.",
    )
    assert blocked.plan is None
    assert blocked.issues
    assert not (await workspace.list_definitions()).items
