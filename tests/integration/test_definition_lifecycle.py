"""Exercise reviewed retirement and coordinated reference repair on a durable model."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    BusinessCode,
    Client,
    ClientConfiguration,
    DefinitionStatus,
    DomainModelBuilder,
    InvalidDecisionError,
    LabelText,
    MeaningText,
    ModelKind,
    Reject,
    StaleStateError,
    ValueSetDefinition,
    ValueSetMember,
    ValueSetMembership,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_unit_retirement_requires_atomic_repair_of_its_active_dependents(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="recruitment",
    )
    model = await project.create_model(
        actor="author",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Existing model.",
    )
    initial = DomainModelBuilder(model_info=model.info)
    hour_id = initial.add_unit(name="hour", meaning="Processing-duration hour.", symbol="h")
    units_id = initial.add_value_set(
        name="duration-units",
        meaning="Codes used for processing duration.",
        membership=ValueSetMembership.CLOSED,
        members=[
            ValueSetMember(
                code=BusinessCode(value="h"),
                label=LabelText(value="Hour"),
                meaning=MeaningText(value="An elapsed hour."),
                unit=hour_id,
            )
        ],
    )
    _ = initial.add_quantity(
        name="duration", meaning="Elapsed processing duration.", units=units_id
    )
    plan = initial.build_change_plan(reason="Establish a local quantity and reviewed unit.")
    case = await model.propose_change_plan(actor="author", plan=plan)
    accept = Accept(reason="The application can use the complete inspected graph.")
    _ = await model.decide_review(actor="reviewer", case=case, decision=accept)

    model = await project.get_model(name=model.info.name)
    hour = await model.get_unit(unit_id=hour_id)
    unit_set = await model.get_definition(definition_id=units_id)
    assert isinstance(unit_set.body, ValueSetDefinition)
    standalone = await model.propose_definition_retirement(
        actor="author",
        definition_id=hour.id,
        expected_revision=hour.revision,
        reason="Review retirement of the old unit identity.",
    )
    assert (await model.preview_changes(case=standalone, decision=accept)).blockers
    with pytest.raises(InvalidDecisionError):
        _ = await model.decide_review(actor="reviewer", case=standalone, decision=accept)
    assert await model.get_unit(unit_id=hour_id) == hour

    repair = DomainModelBuilder(model_info=model.info)
    reporting_hour = repair.add_unit(
        name="reporting-hour", symbol="h", meaning="Hour used in reports."
    )
    repair.edit_definition(
        definition=unit_set,
        body=replace(
            unit_set.body,
            members=[replace(unit_set.body.members[0], unit=reporting_hour)],
        ),
    )
    repair.remove_unit(unit=hour, replacements=[reporting_hour])
    coordinated = await model.propose_change_plan(
        actor="author",
        plan=repair.build_change_plan(reason="Retire the old unit and repair its vocabulary."),
    )
    _ = await model.decide_review(actor="reviewer", case=coordinated, decision=accept)
    retired = await model.get_unit(unit_id=hour_id)
    assert retired.status is DefinitionStatus.RETIRED
    assert retired.id == hour.id
    assert retired.replacement_ids == (reporting_hour,)
    assert (
        await model.get_definition(definition_id=units_id, revision=unit_set.revision) == unit_set
    )
    repaired = await model.get_definition(definition_id=units_id)
    assert isinstance(repaired.body, ValueSetDefinition)
    assert repaired.body.members[0].unit == reporting_hour

    with pytest.raises(StaleStateError):
        _ = await model.decide_review(actor="reviewer", case=standalone, decision=accept)
    _ = await model.decide_review(
        actor="reviewer",
        case=standalone,
        decision=Reject(reason="Superseded by the reviewed repair."),
    )
    model = await project.get_model(name=model.info.name)
    reason = "Restore the retained hour for another measure."
    typed, generic = (DomainModelBuilder(model_info=model.info) for _ in range(2))
    typed.restore_unit(unit=retired)
    generic.restore_definition(definition=retired)
    restore_plan = typed.build_change_plan(reason=reason)
    assert restore_plan.operations == generic.build_change_plan(reason=reason).operations
    restore = await model.propose_change_plan(actor="author", plan=restore_plan)
    _ = await model.decide_review(actor="reviewer", case=restore, decision=accept)
    restored = await model.get_unit(unit_id=hour_id)
    assert restored.status is DefinitionStatus.APPROVED
    assert restored.id == hour.id
    assert restored.replacement_ids == ()
    first = await model.get_definition_history(definition_id=hour_id, limit=1)
    assert first.items == (hour,)
    assert first.next_cursor is not None
    later = await model.get_definition_history(definition_id=hour_id, cursor=first.next_cursor)
    assert tuple(item.status for item in later.items) == (
        DefinitionStatus.RETIRED,
        DefinitionStatus.APPROVED,
    )
