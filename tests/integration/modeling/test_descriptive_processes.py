"""Review and port a process and decision table through the public SDK."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    Activity,
    BusinessDecisionDefinition,
    Client,
    ClientConfiguration,
    Condition,
    DataType,
    DecisionInput,
    DecisionOutput,
    DecisionRule,
    DecisionValue,
    DefinitionKindMismatchError,
    DomainModelBuilder,
    DomainModelBundle,
    Event,
    EventKind,
    Flow,
    FlowKind,
    Gateway,
    GatewayDirection,
    GatewayKind,
    ModelKind,
    ProcessPartNotFoundError,
    Role,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_reviewed_process_retains_typed_edges_and_decision_literals(tmp_path: Path) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="recruitment",
    )
    model = await project.create_model(
        actor="author",
        kind=ModelKind.OBSERVED,
        name="observed",
        description="Reviewed recruitment decisions.",
    )
    builder = DomainModelBuilder(model_info=model.info)
    meaning = builder.add_concept(name="assessment", meaning="An inspected recruitment assessment.")
    significant = Condition(
        name="significant",
        description="A reviewer records a significant risk.",
        expression="risk_recorded",
        input_ids=["risk_recorded"],
    )
    values = (
        ("risk", DecisionValue(value=True)),
        ("score", DecisionValue(value=Decimal("12.30"))),
        ("review-date", DecisionValue(value=date(2024, 7, 12))),
        ("reviewed-at", DecisionValue(value=datetime(2024, 7, 12, 14, tzinfo=UTC))),
    )
    decision = builder.add_definition(
        name="classification",
        meaning="Describe the review outcome after classification.",
        body=BusinessDecisionDefinition(
            inputs=[
                DecisionInput(
                    id="risk_recorded",
                    name="Risk recorded",
                    definition_id=meaning,
                    data_type=DataType.BOOLEAN,
                )
            ],
            outputs=[
                DecisionOutput(id=key, name=key, definition_id=meaning, data_type=value.data_type)
                for key, value in values
            ],
            conditions=[significant],
            rules=[
                DecisionRule(id="qualified", condition_ids=[significant.id], output_values=values)
            ],
        ),
    )
    reviewer = Role(name="reviewer", meaning="Inspect the current risk assessment.")
    start = Event(name="received", kind=EventKind.START)
    task = Activity(
        name="classification-review", roles=[reviewer], inputs=[meaning], decision=decision
    )
    split = Gateway(name="risk-path", kind=GatewayKind.EXCLUSIVE, direction=GatewayDirection.SPLIT)
    end = Event(name="reviewed", kind=EventKind.END)
    _ = builder.add_process(
        name="risk-management",
        meaning="Describe review of recruitment risks.",
        roles=[reviewer],
        activities=[task],
        gateways=[split],
        events=[start, end],
        conditions=[significant],
        flows=[
            Flow(name="begin", source=start, target=task),
            Flow(name="consider", source=task, target=split),
            Flow(
                name="review-again",
                source=split,
                target=task,
                kind=FlowKind.CONDITIONAL,
                condition=significant,
            ),
            Flow(name="record-result", source=split, target=end, kind=FlowKind.DEFAULT),
        ],
    )
    plan = builder.build_change_plan(reason="Describe the assessment process and decision.")
    case = await model.propose_change_plan(actor="author", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    inspected = await model.get_process(name="risk-management")
    assert await model.get_definition(name="risk-management") == inspected
    with pytest.raises(DefinitionKindMismatchError):
        _ = await model.get_process(name="assessment")
    with pytest.raises(ProcessPartNotFoundError):
        _ = inspected.get_event(name="missing")
    prepared = await model.prepare_publication(actor="editor")
    bundle = await model.publish(
        publication=prepared,
        version="1.0.0",
        actor="publisher",
        reason="Release the descriptive model.",
    )
    wire = bundle.serialize()
    assert f'"source_id":"{start.id.value}"'.encode() in wire
    assert b'"lexical_value":"12.3"' in wire
    reopened = DomainModelBundle.deserialize(payload=wire)
    assert reopened == bundle
    restored = reopened.get_process(process_id=inspected.id)
    assert restored == inspected
    assert restored.get_flow(name="begin").source_id == start.id
    activity = restored.get_activity(activity_id=task.id)
    assert activity.decision_id == decision
    assert not activity.referenced_definitions
    assert not activity.referenced_roles
    assert restored.get_condition(name="significant").id == significant.id
