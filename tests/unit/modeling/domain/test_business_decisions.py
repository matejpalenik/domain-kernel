"""Check the structure of descriptive decision tables without evaluating them."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from domain_kernel import (
    BusinessDecisionDefinition,
    Condition,
    DataType,
    DecisionInput,
    DecisionOutput,
    DecisionRule,
    DecisionValue,
    DefinitionId,
    HitPolicy,
    ProcessPartAlreadyExistsError,
)


@pytest.fixture
def catalog_decision() -> BusinessDecisionDefinition:
    definition_id = DefinitionId(value="catalog-item")
    condition = Condition(
        name="identified",
        description="A component number is present.",
        expression="component_number is present",
        input_ids=["component_number"],
    )
    return BusinessDecisionDefinition(
        inputs=[
            DecisionInput(
                id="component_number",
                name="Component number",
                definition_id=definition_id,
                data_type=DataType.STRING,
            )
        ],
        outputs=[
            DecisionOutput(
                id="valid",
                name="Valid catalog entry",
                definition_id=definition_id,
                data_type=DataType.BOOLEAN,
            )
        ],
        conditions=[condition],
        rules=[
            DecisionRule(
                id="accept",
                condition_ids=[condition.id],
                output_values=[("valid", DecisionValue(value=True))],
            )
        ],
    )


def test_decision_value_is_an_exact_native_scalar() -> None:
    local = datetime(2024, 7, 12, 12, tzinfo=timezone(timedelta(hours=2)))
    instant = DecisionValue(value=local)

    assert DecisionValue(value="valid").data_type is DataType.STRING
    assert DecisionValue(value=True).data_type is DataType.BOOLEAN
    assert DecisionValue(value=1).data_type is DataType.INTEGER
    assert DecisionValue(value=Decimal("1.20")).data_type is DataType.DECIMAL
    assert DecisionValue(value=date(2024, 7, 12)).data_type is DataType.DATE
    assert instant.data_type is DataType.DATETIME
    assert type(instant.value) is datetime
    assert instant.value.tzinfo is UTC
    assert instant.value == datetime(2024, 7, 12, 10, tzinfo=UTC)
    with pytest.raises(ValueError, match="finite"):
        _ = DecisionValue(value=Decimal("Infinity"))
    with pytest.raises(ValueError, match="time zone"):
        _ = DecisionValue(value=datetime(2024, 7, 12))  # noqa: DTZ001 - Intentional naive value.


def test_decision_and_rule_detach_their_collections(
    catalog_decision: BusinessDecisionDefinition,
) -> None:
    inputs = list(catalog_decision.inputs)
    outputs = list(catalog_decision.outputs)
    conditions = list(catalog_decision.conditions)
    [original] = catalog_decision.rules
    condition_ids = list(original.condition_ids)
    output_values = list(original.output_values)
    rule = replace(original, condition_ids=condition_ids, output_values=output_values)
    rules = [rule]
    table = replace(
        catalog_decision, inputs=inputs, outputs=outputs, conditions=conditions, rules=rules
    )

    inputs.clear()
    outputs.clear()
    conditions.clear()
    rules.clear()
    condition_ids.clear()
    output_values.clear()

    assert table == catalog_decision
    assert table.rules == (original,)
    assert table.rules[0].output_values == (("valid", DecisionValue(value=True)),)


def test_decision_rule_requires_the_declared_scalar_type(
    catalog_decision: BusinessDecisionDefinition,
) -> None:
    [rule] = catalog_decision.rules
    wrong_type = replace(rule, output_values=[("valid", DecisionValue(value=1))])

    with pytest.raises(ValueError, match="scalar type"):
        _ = replace(catalog_decision, rules=[wrong_type])


def test_decision_condition_symbols_must_be_declared(
    catalog_decision: BusinessDecisionDefinition,
) -> None:
    with pytest.raises(ValueError, match="declared decision input keys"):
        _ = replace(catalog_decision, inputs=[])


def test_decision_rule_must_reference_the_condition_id_not_just_its_name(
    catalog_decision: BusinessDecisionDefinition,
) -> None:
    [condition] = catalog_decision.conditions
    same_name = Condition(
        name=condition.name,
        description=condition.description,
        expression=condition.expression,
        input_ids=condition.input_ids,
    )

    with pytest.raises(ValueError, match="exact referenced condition"):
        _ = replace(catalog_decision, conditions=[same_name])
    with pytest.raises(ProcessPartAlreadyExistsError):
        _ = replace(catalog_decision, conditions=[condition, same_name])


@pytest.mark.parametrize("hit_policy", [HitPolicy.UNIQUE, HitPolicy.FIRST, HitPolicy.COLLECT])
def test_hit_policy_retains_rule_order_and_only_unique_rejects_identical_condition_sets(
    catalog_decision: BusinessDecisionDefinition, hit_policy: HitPolicy
) -> None:
    [condition] = catalog_decision.conditions
    extra = Condition(
        name="current",
        description="The entry is current.",
        expression="record is current",
    )
    [rule] = catalog_decision.rules
    first = replace(rule, condition_ids=[condition.id, extra.id])
    second = DecisionRule(
        id="reject",
        condition_ids=[extra.id, condition.id],
        output_values=[("valid", DecisionValue(value=False))],
    )
    if hit_policy is HitPolicy.UNIQUE:
        with pytest.raises(ValueError, match="identical rule conditions"):
            _ = replace(catalog_decision, conditions=[condition, extra], rules=[first, second])
        return

    table = replace(
        catalog_decision,
        conditions=[condition, extra],
        rules=[first, second],
        hit_policy=hit_policy,
    )

    assert table.hit_policy is hit_policy
    assert table.rules == (first, second)
