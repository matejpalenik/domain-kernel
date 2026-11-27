"""Verify canonical encoding and restoration of persisted SDK records."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from domain_kernel import (
    ArtifactWriteRequest,
    AttributeDefinition,
    BusinessCode,
    ChangePlanId,
    CollectionKind,
    ConceptDefinition,
    ContentHash,
    Count,
    DecimalFacets,
    DecimalPrecision,
    DecimalScale,
    Definition,
    DefinitionId,
    DependencyChangeIntent,
    LabelText,
    MeaningText,
    ModelChangePlan,
    ModelId,
    ModelScope,
    ModelVersion,
    ProjectId,
    SchemaDiscoveryOptions,
    ValueSetDefinition,
    ValueSetMember,
    ValueSetMembership,
)
from domain_kernel.discovery.domain.models import DiscoveryRun
from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.hashing import Hashing
from tests.support.modeling.machine_definition import make_machine_definition


def test_artifact_write_keeps_its_canonical_metadata() -> None:
    """Preserve the bytes that identify saved artifacts and export retry requests."""
    request = ArtifactWriteRequest(
        project_id=ProjectId(value="project"),
        model_id=None,
        store="artifacts",
        key="projects/project/model.json",
        media_type="application/json",
        expected_hash=ContentHash(value="sha256:" + "a" * 64),
    )
    content = (
        b'{"record":{"fields":{"consumer_obligations":[],"expected_hash":{"fields":'
        b'{"value":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
        b'"record":"ContentHash"},"key":"projects/project/model.json","media_type":"application/json",'
        b'"model_id":null,"project_id":{"fields":{"value":"project"},"record":"ProjectId"},'
        b'"projection_limits":[],"semantic":null,"store":"artifacts"},'
        b'"record":"ArtifactWrite"},"version":1}'
    )

    assert RecordCodec.encode(value=request, root_type=ArtifactWriteRequest) == content
    assert (
        RecordCodec.decode(
            content=content, expected=ArtifactWriteRequest, root_type=ArtifactWriteRequest
        )
        == request
    )


def test_dependency_change_keeps_its_canonical_plan_encoding() -> None:
    """Preserve the canonical encoding of dependency changes embedded in saved plans."""
    project_id = ProjectId(value="project")
    pin = ModelVersion(
        scope=ModelScope(project_id=project_id, model_id=ModelId(value="asset-vocabulary")),
        version="1.0.0",
        content_hash=ContentHash(value="sha256:" + "a" * 64),
    )
    plan = ModelChangePlan(
        id=ChangePlanId(value="dependency-plan"),
        scope=ModelScope(project_id=project_id, model_id=ModelId(value="consumer")),
        expected_workspace_revision=0,
        reason="Adopt asset vocabulary.",
        bindings=(),
        operations=(),
        dependency_change=DependencyChangeIntent(before=(), after=(pin,)),
    )

    content = RecordCodec.encode(value=plan)
    assert Hashing.hash_bytes(content=content) == ContentHash(
        value="sha256:1b8127088a1cacfc26edca4659d5f8598c04425b491ba122e472fb104f87f255"
    )
    assert RecordCodec.decode(content=content, expected=ModelChangePlan) == plan


def test_definition_record_round_trips_bounds_decimal_and_nominal_unit_links() -> None:
    definition = make_machine_definition()
    amount = AttributeDefinition.decimal(
        name="amount",
        required=False,
        collection=CollectionKind.LIST,
        max_items=Count(value=4),
        facets=DecimalFacets(precision=DecimalPrecision(value=5), scale=DecimalScale(value=2)),
    )
    concept = replace(definition, body=ConceptDefinition(attributes=[amount]))
    units = replace(
        definition,
        body=ValueSetDefinition(
            membership=ValueSetMembership.CLOSED,
            members=[
                ValueSetMember(
                    code=BusinessCode(value="h"),
                    label=LabelText(value="Hour"),
                    meaning=MeaningText(value="An hour of elapsed time."),
                    unit=DefinitionId(value="hour"),
                )
            ],
        ),
    )

    for record in (concept, units):
        wire = RecordCodec.encode(value=record)
        assert RecordCodec.decode(content=wire, expected=Definition) == record
        with pytest.raises(ValueError, match="canonical"):
            _ = RecordCodec.decode(content=wire + b" ", expected=Definition)


def test_pre_schema_discovery_checkpoint_is_rejected() -> None:
    """Reject a saved run that omits fields required by the current encoding."""
    payload = (Path(__file__).parent / "fixtures/discovery_pre_schema.json").read_bytes()
    content = payload.removesuffix(b"\n")

    with pytest.raises(ValueError, match="canonical"):
        _ = RecordCodec.decode(content=content, expected=DiscoveryRun)


def test_v23_discovery_options_are_rejected() -> None:
    """Reject options carrying the retired workflow selectors."""
    content = CanonicalJson.encode(
        value={
            "version": 1,
            "record": {
                "record": "SchemaDiscoveryOptions",
                "fields": {
                    "as_of": None,
                    "competency_questions": [],
                    "source_context": [],
                    "workflow_version": "v23",
                    "coverage_strategy": "focused",
                    "reference_guidance": "late_mapping",
                },
            },
        },
    )

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        _ = RecordCodec.decode(content=content, expected=SchemaDiscoveryOptions)
