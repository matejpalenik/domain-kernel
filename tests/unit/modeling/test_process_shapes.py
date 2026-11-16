"""Verify local workflow identity and typed decision literals."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from domain_kernel import (
    Activity,
    ActivityId,
    BusinessDecisionDefinition,
    Condition,
    DataType,
    DecisionOutput,
    DecisionRule,
    DecisionValue,
    DefinitionId,
    Event,
    EventKind,
    Flow,
    FlowKind,
    Gateway,
    GatewayDirection,
    GatewayKind,
    ProcessDefinition,
    ProcessPartAlreadyExistsError,
    Role,
)


def test_process_keeps_explicit_nominal_children_and_detaches_lists() -> None:
    editor = Role(name="editor", meaning="Reviews the recruited system.")
    created = Event(name="created", kind=EventKind.START)
    review = Activity(name="review", roles=[editor])
    complete = Event(name="completed", kind=EventKind.END)
    activities = [review]
    body = ProcessDefinition(
        activities=activities,
        events=[created, complete],
        roles=[editor],
        flows=[
            Flow(name="start-review", source=created, target=review),
            Flow(name="end-review", source=review.id, target=complete.id),
        ],
    )
    activities.clear()
    assert body.activities == (review,)
    assert body.activities[0].role_ids == (editor.id,)
    assert body.flows[0].source_id == created.id
    assert type(body.flows[0].target_id) is ActivityId
    assert body.flows[1].target_id == complete.id


def test_process_rejects_duplicate_names_and_omitted_referenced_parts() -> None:
    editor = Role(name="reviewer", meaning="Inspects the submitted system.")
    start = Event(name="submitted", kind=EventKind.START)
    task = Activity(name="reviewer", roles=[editor])
    end = Event(name="decided", kind=EventKind.END)
    flows = [
        Flow(name="begin", source=start, target=task),
        Flow(name="finish", source=task, target=end),
    ]
    with pytest.raises(ProcessPartAlreadyExistsError):
        _ = ProcessDefinition(activities=[task], roles=[editor], events=[start, end], flows=flows)
    with pytest.raises(ValueError, match="role"):
        _ = ProcessDefinition(activities=[task], roles=[], events=[start, end], flows=flows)


def test_condition_input_symbols_remain_distinct_from_generated_ids() -> None:
    condition = Condition(
        name="significant-risk",
        description="Record the reviewer's assessment.",
        expression="significant_risk",
        input_ids=["significant_risk"],
    )
    assert condition.input_ids == ("significant_risk",)
    assert condition.id.value != condition.name


def test_decision_value_is_an_exact_native_scalar() -> None:
    assert DecisionValue(value=True).data_type is DataType.BOOLEAN
    assert DecisionValue(value=1).data_type is DataType.INTEGER
    assert DecisionValue(value=Decimal("1.20")).data_type is DataType.DECIMAL
    assert DecisionValue(value=date(2024, 7, 12)).data_type is DataType.DATE
    assert DecisionValue(value=datetime(2024, 7, 12, tzinfo=UTC)).data_type is DataType.DATETIME
    with pytest.raises(ValueError, match="finite"):
        _ = DecisionValue(value=Decimal("Infinity"))
    with pytest.raises(ValueError, match="time zone"):
        _ = DecisionValue(value=datetime(2024, 7, 12))  # noqa: DTZ001 - Intentional naive value.


def test_exclusive_gateway_requires_one_default_and_local_endpoints() -> None:
    start = Event(name="begin", kind=EventKind.START)
    review = Activity(name="review")
    finish = Event(name="complete", kind=EventKind.END)
    split = Gateway(name="route", direction=GatewayDirection.SPLIT, kind=GatewayKind.EXCLUSIVE)
    condition = Condition(
        name="qualifies",
        description="Describe when the input qualifies.",
        expression="reviewed_input_qualifies",
    )
    flows = (
        Flow(name="begin-routing", source=start, target=split),
        Flow(
            name="review-qualified-input",
            source=split,
            target=review,
            kind=FlowKind.CONDITIONAL,
            condition=condition,
        ),
        Flow(
            name="complete-otherwise",
            source=split,
            target=finish,
            kind=FlowKind.CONDITIONAL,
            condition=condition,
        ),
        Flow(name="complete-review", source=review, target=finish),
    )
    with pytest.raises(ValueError, match="exactly one default"):
        _ = ProcessDefinition(
            activities=[review],
            events=[start, finish],
            roles=[],
            gateways=[split],
            flows=flows,
            conditions=[condition],
        )
    with pytest.raises(ValueError, match="flow endpoints"):
        _ = ProcessDefinition(
            activities=[],
            events=[start, finish],
            roles=[],
            gateways=[split],
            flows=flows,
            conditions=[condition],
        )


def test_decision_rule_requires_the_declared_scalar_type() -> None:
    output = DecisionOutput(
        id="risk-found",
        name="Risk found",
        definition_id=DefinitionId(value="risk"),
        data_type=DataType.BOOLEAN,
    )
    with pytest.raises(ValueError, match="scalar type"):
        _ = BusinessDecisionDefinition(
            conditions=[],
            inputs=[],
            outputs=[output],
            rules=[
                DecisionRule(
                    id="integer-is-not-boolean",
                    condition_ids=[],
                    output_values=[("risk-found", DecisionValue(value=1))],
                ),
            ],
        )
