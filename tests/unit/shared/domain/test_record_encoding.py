"""Verify canonical record encoding of domain definitions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from domain_kernel import (
    AttributeDefinition,
    BusinessCode,
    CollectionKind,
    ConceptDefinition,
    Count,
    DecimalFacets,
    DecimalPrecision,
    DecimalScale,
    Definition,
    DefinitionId,
    LabelText,
    MeaningText,
    RunStatus,
    SourceRevisionId,
    ValueSetDefinition,
    ValueSetMember,
    ValueSetMembership,
)
from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.models import DiscoveryRun
from tests.support.modeling.machine_definition import make_machine_definition


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
        wire = record_bytes(value=record)
        assert read_record(content=wire, expected=Definition) == record
        with pytest.raises(ValueError, match="canonical"):
            _ = read_record(content=wire + b" ", expected=Definition)


def test_pre_schema_discovery_record_keeps_the_exact_checkpoint() -> None:
    # Captured from dk_discovery_run after running discover() with the writer at 325d3a9.
    payload = (Path(__file__).parent / "fixtures/discovery_pre_schema.json").read_bytes()
    content = payload.removesuffix(b"\n")
    run = read_record(content=content, expected=DiscoveryRun)

    assert run.schema_version is None
    assert run.snapshot.parent_run_id is None
    assert run.actor == "editor"
    assert run.snapshot.status is RunStatus.NEEDS_REVIEW
    assert run.snapshot.id == DiscoveryRunId(value="01c316bcb779459baf09969ab319ec91")
    assert run.snapshot.discovery_id == DiscoveryDraftId(value="9dea5cdc632a48368add0ab0559c296d")
    assert run.snapshot.prompt.effective_instructions == "Read the lookup code."
    (checkpoint,) = run.tasks
    assert checkpoint.source.revision_id == SourceRevisionId(
        value="sha256:5b343859dbe860caa82af5af0cdc0d86338a63fec84b8fabeafe3fc0951349fc"
    )
    assert checkpoint.failure is None
    with pytest.raises(ValueError, match="canonical"):
        _ = read_record(content=content + b" ", expected=DiscoveryRun)
