"""Copy and compare exact published recruitment snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AttributeDefinition,
    BundleId,
    BusinessCode,
    Client,
    ClientConfiguration,
    CollectionKind,
    ComparisonKind,
    Compatibility,
    ConceptReferenceType,
    Count,
    DomainModelBuilder,
    DomainModelBundle,
    InvalidBundleError,
    KeyDefinition,
    LabelText,
    MeaningText,
    ModelKind,
    PinnedDefinitionReference,
    PublicationNotFoundError,
    ScopeMismatchError,
    ValueSetDefinition,
    ValueSetMember,
    ValueSetMembership,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import Model, ModelChangePlan

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _review(*, model: Model, plan: ModelChangePlan) -> None:
    case = await model.propose_change_plan(actor="editor", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))


async def test_copy_exact_bundle_and_compare_authored_shape_change(tmp_path: Path) -> None:
    client = Client(config=ClientConfiguration(base_dir=tmp_path))
    project = await client.create_project(actor="editor", name="recruitment")
    observed = await project.create_model(
        actor="editor",
        kind=ModelKind.OBSERVED,
        description="Current recruitment design.",
        name="observed",
    )
    builder = DomainModelBuilder(model_info=observed.info)
    registry_key = AttributeDefinition.string(name="registry-key", required=True)
    _ = builder.add_concept(
        name="recruitment-ai-system",
        meaning="A system used for employment recruitment.",
        attributes=(
            registry_key,
            AttributeDefinition.string(
                name="purpose",
                collection=CollectionKind.LIST,
                max_items=Count(value=3),
            ),
        ),
        keys=(KeyDefinition(name="registry", attributes=[registry_key.id]),),
    )
    await _review(model=observed, plan=builder.build_change_plan(reason="Review current shape."))
    observed_preparation = await observed.prepare_publication(actor="editor")
    assert observed_preparation.changes.comparison is ComparisonKind.INITIAL
    source = await observed.publish(
        publication=observed_preparation,
        version="1.0.0",
        actor="owner",
        reason="Record the reviewed observed design.",
    )
    received = DomainModelBundle.deserialize(payload=source.serialize())
    proposed = await project.create_model(
        actor="editor",
        kind=ModelKind.PROPOSED,
        name="proposed",
        description="A separate design with revised purpose bounds.",
        copy_from=received,
    )
    reopened = await client.get_project(name=project.name)
    proposed = await reopened.get_model(name="proposed")
    original = source.get_concept(name="recruitment-ai-system")
    copied = await proposed.get_concept(name=original.name)
    assert proposed.info.baseline == source.model_version
    assert copied.id != original.id
    assert copied.baseline_definition_id == original.id
    assert not copied.decision_ids
    assert copied.get_key(name="registry").attributes == (
        copied.get_attribute(name="registry-key").id,
    )
    assert copied.get_key(name="registry").id != original.get_key(name="registry").id

    initial = await proposed.compile(actor="editor")
    comparison = await proposed.diff(before=source, after=initial)
    assert comparison.comparison is ComparisonKind.BASELINE
    assert not comparison.changes
    assert len(comparison.correspondences) == 1

    edit = DomainModelBuilder(model_info=proposed.info)
    edit.edit_attribute(
        concept=copied,
        attribute=copied.get_attribute(name="purpose"),
        max_items=Count(value=2),
    )
    await _review(model=proposed, plan=edit.build_change_plan(reason="Review narrower purposes."))
    captured = await proposed.compile(actor="editor")
    change = await proposed.diff(before=source.model_version, after=captured)
    assert change.before == source.model_version
    assert change.comparison is ComparisonKind.BASELINE
    assert len(change.changes) == 1
    assert change.compatibility is Compatibility.BREAKING
    prepared = await proposed.prepare_publication(actor="editor")
    assert prepared.changes.changes == change.changes
    assert prepared.changes.before == source.model_version
    release = await proposed.publish(
        publication=prepared,
        version="1.0.0",
        actor="owner",
        reason="Release the proposed design.",
    )
    assert (await proposed.diff(before=source, after=release)) == (
        await proposed.diff(before=source.model_version, after=release.model_version)
    )
    latest_preparation = await proposed.prepare_publication(actor="editor")
    assert latest_preparation.changes.before == release.model_version
    assert latest_preparation.changes.comparison is ComparisonKind.REVISION
    assert not latest_preparation.changes.changes
    future_source = await observed.publish(
        publication=await observed.prepare_publication(actor="editor"),
        version="1.1.0",
        actor="owner",
        reason="Release the next source version.",
    )
    await _assert_exact_baseline(
        proposed=proposed,
        source=source,
        newer=future_source,
        release=release,
    )
    assert (await project.get_model(name="proposed")).info.baseline == source.model_version
    assert await observed.get_version(version="1.0.0") == source


async def _assert_exact_baseline(
    *,
    proposed: Model,
    source: DomainModelBundle,
    newer: DomainModelBundle,
    release: DomainModelBundle,
) -> None:
    with pytest.raises(ScopeMismatchError):
        _ = await proposed.diff(before=newer, after=release)
    with pytest.raises(ScopeMismatchError):
        _ = await proposed.diff(before=source.publication.candidate, after=release)
    with pytest.raises(ScopeMismatchError):
        _ = await proposed.diff(before=source, after=source)


async def test_copy_preserves_qualified_edges_and_remaps_units(tmp_path: Path) -> None:
    client = Client(config=ClientConfiguration(base_dir=tmp_path))
    project = await client.create_project(actor="editor", name="recruitment")
    shared = await project.create_model(
        actor="editor",
        name="reference",
        kind=ModelKind.PROPOSED,
        description="Shared terms.",
    )
    author = DomainModelBuilder(model_info=shared.info)
    _ = author.add_concept(name="resource", meaning="A shared reference resource.")
    await _review(model=shared, plan=author.build_change_plan(reason="Review the resource."))
    original_shared = await shared.publish(
        publication=await shared.prepare_publication(actor="editor"),
        version="1.0.0",
        actor="owner",
        reason="Share the resource.",
    )
    source_model = await project.create_model(
        actor="editor",
        name="source",
        kind=ModelKind.OBSERVED,
        description="Local shapes.",
        dependencies=(original_shared.model_version,),
    )
    builder = DomainModelBuilder(model_info=source_model.info)
    hour = builder.add_unit(name="hour", meaning="Elapsed hours.", symbol="h")
    _ = builder.add_value_set(
        name="time-unit",
        meaning="Allowed units of elapsed time.",
        membership=ValueSetMembership.CLOSED,
        members=[
            ValueSetMember(
                code=BusinessCode(value="hour"),
                label=LabelText(value="Hour"),
                meaning=MeaningText(value="An elapsed hour."),
                unit=hour,
            ),
        ],
    )
    resource = original_shared.get_concept(name="resource")
    reference = PinnedDefinitionReference(
        model=original_shared.model_version,
        definition_id=resource.id,
        definition_revision=resource.revision,
    )
    _ = builder.add_concept(
        name="record",
        meaning="A local recruitment record.",
        attributes=[AttributeDefinition.reference(name="resource", target=reference)],
    )
    await _review(
        model=source_model, plan=builder.build_change_plan(reason="Review the local shapes.")
    )
    source = await source_model.publish(
        publication=await source_model.prepare_publication(actor="editor"),
        version="1.0.0",
        actor="owner",
        reason="Release the local vocabulary.",
    )
    copy = await project.create_model(
        actor="editor",
        name="copy",
        kind=ModelKind.PROPOSED,
        description="An independent version.",
        copy_from=source,
    )
    candidate = await copy.compile(actor="editor")
    copied_book = {item.name: item for item in candidate.content.definitions}
    assert candidate.dependency_bundles == (original_shared,)
    copied_set = copied_book["time-unit"].body
    assert isinstance(copied_set, ValueSetDefinition)
    assert copied_set.members[0].unit == copied_book["hour"].id
    assert copied_book["hour"].id != hour
    copied_record = await copy.get_concept(name="record")
    assert copied_record.get_attribute(name="resource").value_type == ConceptReferenceType(
        concept=reference,
    )
    assert not (await copy.diff(before=source, after=candidate)).changes

    foreign = await client.create_project(actor="editor", name="foreign")
    unregistered = DomainModelBundle.from_approved(
        publication=source.publication,
        approval=source.approval,
        now=source.published_at,
        version="unregistered",
        bundle_id=BundleId(value="unregistered"),
    )
    forged = DomainModelBundle.from_approved(
        publication=source.publication,
        approval=source.approval,
        now=source.published_at,
        version=source.version,
        bundle_id=BundleId(value="altered"),
    )
    with pytest.raises(PublicationNotFoundError):
        _ = await project.create_model(
            actor="editor",
            name="bad-copy",
            kind=ModelKind.PROPOSED,
            description="Invalid.",
            copy_from=unregistered,
        )
    with pytest.raises(InvalidBundleError):
        _ = await project.create_model(
            actor="editor",
            name="bad-copy",
            kind=ModelKind.PROPOSED,
            description="Invalid.",
            copy_from=forged,
        )
    with pytest.raises(ScopeMismatchError):
        _ = await foreign.create_model(
            actor="editor",
            name="bad-copy",
            kind=ModelKind.PROPOSED,
            description="Invalid.",
            copy_from=source,
        )
    assert "bad-copy" not in {item.name for item in (await project.list_models()).items}
    assert not (await foreign.list_models()).items
