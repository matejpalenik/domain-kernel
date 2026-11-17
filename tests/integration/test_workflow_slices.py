"""Publish the real shared quantity graph before selecting a workflow slice."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AttributeDefinition,
    BusinessCode,
    Client,
    ClientConfiguration,
    DomainModelBuilder,
    InvalidBundleError,
    LabelText,
    MeaningText,
    ModelKind,
    PinnedDefinitionReference,
    ResourceLimitError,
    ScopeMismatchError,
    StructuredValueType,
    TraversalDirection,
    ValueSetMember,
    ValueSetMembership,
    compose_models,
    slice_model,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import DomainModelBundle, Model

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _release(*, model: Model, builder: DomainModelBuilder, version: str) -> DomainModelBundle:
    plan = builder.build_change_plan(reason="Review the published shape.")
    case = await model.propose_change_plan(actor="author", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    return await model.publish(
        publication=await model.prepare_publication(actor="editor"),
        version=version,
        actor="owner",
        reason="Publish the reviewed business definitions.",
    )


async def test_select_exact_workflow_and_close_external_vocabulary_and_unit(tmp_path: Path) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="recruitment",
    )
    module = await project.create_model(
        actor="author",
        name="quantities",
        kind=ModelKind.PROPOSED,
        description="Shared quantity shapes.",
    )
    authored = DomainModelBuilder(model_info=module.info)
    _ = authored.add_concept(name="assessment", meaning="A generic shared assessment.")
    hour = authored.add_unit(name="hour", meaning="An elapsed hour.", symbol="h")
    vocabulary = authored.add_value_set(
        name="duration-unit",
        meaning="Available units for elapsed duration.",
        membership=ValueSetMembership.CLOSED,
        members=[
            ValueSetMember(
                code=BusinessCode(value="h"),
                label=LabelText(value="Hour"),
                meaning=MeaningText(value="One hour."),
                unit=hour,
            ),
        ],
    )
    duration = authored.add_quantity(
        display_name="Duration",
        meaning="Measured elapsed time.",
        units=vocabulary,
    )
    support = await _release(model=module, builder=authored, version="1.0.0")
    shared_duration = next(item for item in support.content.definitions if item.id == duration)
    pinned_duration = PinnedDefinitionReference(
        model=support.model_version,
        definition_id=duration,
        definition_revision=shared_duration.revision,
    )
    model = await project.create_model(
        actor="author",
        name="recruitment",
        kind=ModelKind.PROPOSED,
        description="Application-specific assessment.",
        dependencies=[support.model_version],
    )
    local = DomainModelBuilder(model_info=model.info)
    _ = local.add_concept(
        name="assessment",
        meaning="Measure a completed recruitment assessment.",
        attributes=[
            AttributeDefinition(
                name="duration",
                value_type=StructuredValueType(structure=pinned_duration),
                required=True,
            )
        ],
    )
    released = await _release(model=model, builder=local, version="1.0.0")
    _assert_slice(support=support, released=released)

    other_version = await model.publish(
        publication=await model.prepare_publication(actor="editor"),
        version="1.1.0",
        actor="owner",
        reason="Publish a separate exact release.",
    )
    with pytest.raises(InvalidBundleError) as conflict:
        _ = compose_models(bundles=[released, other_version])
    assert conflict.value.issues[0].code == "composition_conflict"
    foreign = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="unrelated",
    )
    foreign_model = await foreign.create_model(
        actor="author",
        name="other",
        kind=ModelKind.PROPOSED,
        description="Another project.",
    )
    foreign_builder = DomainModelBuilder(model_info=foreign_model.info)
    _ = foreign_builder.add_concept(name="assessment", meaning="An unrelated assessment.")
    foreign_release = await _release(model=foreign_model, builder=foreign_builder, version="1.0.0")
    with pytest.raises(ScopeMismatchError):
        _ = compose_models(bundles=[released, foreign_release])


def _assert_slice(*, support: DomainModelBundle, released: DomainModelBundle) -> None:
    original_bytes = released.serialize()
    composition = compose_models(bundles=[released, support, released])
    assert composition == compose_models(bundles=[support, released])
    assert {archive.model_version for archive in composition.bundles} == {
        released.model_version,
        support.model_version,
    }
    local = released.get_concept(name="assessment")
    upstream = support.get_concept(name=local.name)
    assert local.id != upstream.id
    seed = PinnedDefinitionReference(
        model=released.model_version,
        definition_id=local.id,
        definition_revision=local.revision,
    )
    selected = slice_model(composition=composition, seeds=[seed])
    assert tuple(item.reference for item in selected.selected) == (seed,)
    assert {item.definition.name for item in selected.support} == {
        "duration",
        "duration-unit",
        "hour",
    }
    assert all(item.reference.model == support.model_version for item in selected.support)
    assert set(selected.models) == {released.model_version, support.model_version}
    assert not selected.issues
    expanded = slice_model(
        composition=composition,
        seeds=[seed],
        max_hops=1,
        direction=TraversalDirection.OUTGOING,
    )
    assert {item.definition.name for item in expanded.selected} == {"assessment", "duration"}
    duration = next(
        item.reference for item in selected.support if item.definition.name == "duration"
    )
    reverse = slice_model(
        composition=composition,
        seeds=[duration],
        max_hops=1,
        direction=TraversalDirection.INCOMING,
    )
    assert {item.reference for item in reverse.selected} == {seed, duration}
    assert {item.definition.name for item in reverse.support} == {"duration-unit", "hour"}
    with pytest.raises(ResourceLimitError):
        _ = slice_model(composition=composition, seeds=[seed], max_definitions=1)
    with pytest.raises(ResourceLimitError):
        _ = slice_model(composition=composition, seeds=[seed], max_bytes=1)
    with pytest.raises(ResourceLimitError):
        _ = compose_models(bundles=[released], max_bytes=1)
    with pytest.raises(ValueError, match="active"):
        _ = slice_model(composition=composition, seeds=[replace(seed, definition_revision=2)])
    with pytest.raises(InvalidBundleError):
        _ = compose_models(bundles=[replace(released, version="substituted")])
    assert released.serialize() == original_bytes
