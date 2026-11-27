"""Exercise exact published references through creation, review and portable consumption."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AttributeDefinition,
    CaseStatus,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    ConceptReferenceType,
    DefinitionId,
    DependencyChangeIntent,
    DependencyRemapping,
    DomainModelBuilder,
    DomainModelBundle,
    InvalidDecisionError,
    ModelKind,
    PinnedDefinitionReference,
    PublicationNotFoundError,
    Reject,
    ScopeMismatchError,
    StaleStateError,
)
from domain_kernel.modeling.domain.dependencies import dependency_closure
from domain_kernel.modeling.domain.errors.invalid_bundle_error import InvalidBundleError
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import Model, ModelChangePlan, ModelVersion, Project, Publication, ReviewCase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _review(*, model: Model, plan: ModelChangePlan) -> None:
    case = await model.propose_change_plan(actor="author", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))


async def _publish(*, model: Model, version: str) -> DomainModelBundle:
    prepared = await model.prepare_publication(actor="editor")
    return await model.publish(
        publication=prepared,
        version=version,
        actor="owner",
        reason="Release reviewed vocabulary.",
    )


async def test_exact_dependency_survives_an_upstream_edit_and_independent_reload(
    tmp_path: Path,
) -> None:
    config = ClientConfiguration(base_dir=tmp_path)
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    shared = await project.create_model(
        actor="author",
        kind=ModelKind.OBSERVED,
        name="shared",
        description="Shared legislative definitions.",
    )
    author = DomainModelBuilder(model_info=shared.info)
    _ = author.add_concept(name="legal-resource", meaning="An addressable original legal resource.")
    await _review(
        model=shared, plan=author.build_change_plan(reason="Review the reference vocabulary.")
    )
    original = await _publish(model=shared, version="1.0.0")
    resource = original.get_concept(name="legal-resource")
    dependency = PinnedDefinitionReference(
        model=original.model_version,
        definition_id=resource.id,
        definition_revision=resource.revision,
    )
    local = await project.create_model(
        actor="author",
        kind=ModelKind.PROPOSED,
        name="recruitment",
        description="Recruitment uses the shared legal resource.",
        dependencies=[original.model_version],
    )
    edit = DomainModelBuilder(model_info=local.info)
    _ = edit.add_concept(
        name="recruitment-source",
        meaning="The source of a recruitment interpretation.",
        attributes=[AttributeDefinition.reference(name="source", required=True, target=dependency)],
    )
    await _review(
        model=local, plan=edit.build_change_plan(reason="Link the exact shared revision.")
    )
    updated_model = await project.get_model(name=shared.info.name)
    updated = DomainModelBuilder(model_info=updated_model.info)
    updated.edit_definition(definition=resource, meaning="An edited legal resource definition.")
    await _review(
        model=updated_model, plan=updated.build_change_plan(reason="Review the upstream edit.")
    )
    newer = await _publish(model=updated_model, version="1.1.0")
    assert newer.model_version != original.model_version

    reopened = await Client(config=config).get_project(name=project.name)
    local = await reopened.get_model(name=local.info.name)
    assert local.info.dependencies == (original.model_version,)
    released = await _publish(model=local, version="1.0.0")
    consumer = DomainModelBundle.deserialize(payload=released.serialize())
    restored = consumer.publication.candidate
    assert restored.dependencies == (original.model_version,)
    assert restored.dependency_bundles == (original,)
    assert restored.dependency_bundles[0].get_concept(concept_id=resource.id) == resource
    restored_field = consumer.get_concept(name="recruitment-source").get_attribute(name="source")
    assert restored_field.value_type == ConceptReferenceType(concept=dependency)


async def _authored_model(
    *,
    project: Project,
    name: str,
    dependencies: tuple[ModelVersion, ...] = (),
) -> Model:
    model = await project.create_model(
        actor="author",
        kind=ModelKind.PROPOSED,
        name=name,
        description="An independently owned vocabulary.",
        dependencies=dependencies,
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_concept(
        name="legal-resource",
        meaning="One meaning developed in this model's scope.",
    )
    await _review(model=model, plan=builder.build_change_plan(reason="Review the local meaning."))
    return model


async def test_diamond_shares_one_exact_pin_and_rejects_competing_versions(tmp_path: Path) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="legislation",
    )
    shared = await _authored_model(project=project, name="shared")
    first = await _publish(model=shared, version="1.0.0")
    second = await _publish(model=shared, version="1.1.0")
    left = await _publish(
        model=await _authored_model(
            project=project, name="left", dependencies=(first.model_version,)
        ),
        version="1.0.0",
    )
    right = await _publish(
        model=await _authored_model(
            project=project, name="right", dependencies=(first.model_version,)
        ),
        version="1.0.0",
    )
    conflicting = await _publish(
        model=await _authored_model(
            project=project,
            name="conflicting",
            dependencies=(second.model_version,),
        ),
        version="1.0.0",
    )
    consumer = await _publish(
        model=await _authored_model(
            project=project,
            name="diamond",
            dependencies=(left.model_version, right.model_version),
        ),
        version="1.0.0",
    )
    loaded = DomainModelBundle.deserialize(payload=consumer.serialize())
    closure = dependency_closure(
        scope=loaded.scope,
        bundles=loaded.publication.candidate.dependency_bundles,
    )
    assert tuple(item.model_version for item in closure) == (
        left.model_version,
        first.model_version,
        right.model_version,
    )
    graph = (loaded, *closure)
    assert len({item.get_concept(name="legal-resource").id for item in graph}) == len(graph)
    with pytest.raises(InvalidBundleError) as collision:
        _ = await _authored_model(
            project=project,
            name="ambiguous",
            dependencies=(left.model_version, conflicting.model_version),
        )
    assert collision.value.issues[0].code == "dependency_conflict"
    with pytest.raises(InvalidBundleError) as cycle:
        _ = dependency_closure(scope=shared.scope, bundles=(left,))
    assert cycle.value.issues[0].code == "dependency_cycle"
    assert "ambiguous" not in {info.name for info in (await project.list_models()).items}
    work = await project.get_model(name="diamond")
    with pytest.raises(InvalidBundleError) as upgrade_collision:
        _ = await _prepare_upgrade(
            model=work,
            change=DependencyChangeIntent(
                before=work.info.dependencies,
                after=[left.model_version, conflicting.model_version],
            ),
            reason="Inspect an incompatible transitive selection.",
        )
    assert upgrade_collision.value.issues[0].code == "dependency_conflict"
    assert (await project.get_model(name="diamond")).info == work.info


async def test_missing_hash_substituted_and_foreign_pins_reject_creation(tmp_path: Path) -> None:
    client = Client(config=ClientConfiguration(base_dir=tmp_path))
    project = await client.create_project(actor="author", name="local")
    foreign = await client.create_project(actor="author", name="foreign")
    shared = await _authored_model(project=project, name="shared")
    release = await _publish(model=shared, version="1.0.0")
    pin = release.model_version

    with pytest.raises(PublicationNotFoundError):
        _ = await _authored_model(
            project=project,
            name="missing",
            dependencies=(replace(pin, version="2.0.0"),),
        )
    with pytest.raises(ScopeMismatchError):
        _ = await _authored_model(project=foreign, name="foreign-model", dependencies=(pin,))
    with pytest.raises(InvalidBundleError) as substituted:
        _ = await _authored_model(
            project=project,
            name="substituted",
            dependencies=(replace(pin, content_hash=Hashing.hash_bytes(content=b"substitution")),),
        )
    assert substituted.value.issues[0].code == "dependency_pin"
    assert tuple(info.name for info in (await project.list_models()).items) == ("shared",)
    assert not (await foreign.list_models()).items


async def test_stale_missing_and_retired_qualified_targets_cannot_pass_review(
    tmp_path: Path,
) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="legislation",
    )
    upstream = await _authored_model(project=project, name="shared")
    upstream = await project.get_model(name=upstream.info.name)
    original = await upstream.get_concept(name="legal-resource")
    retirement = DomainModelBuilder(model_info=upstream.info)
    _ = retirement.add_concept(name="replacement", meaning="A separate active concept.")
    retirement.remove_concept(concept=original)
    await _review(
        model=upstream,
        plan=retirement.build_change_plan(reason="Retire the unused meaning."),
    )
    archive = await _publish(model=upstream, version="1.0.0")
    retired = archive.get_concept(concept_id=original.id)
    active = archive.get_concept(name="replacement")
    local = await _authored_model(
        project=project,
        name="consumer",
        dependencies=(archive.model_version,),
    )
    local = await project.get_model(name=local.info.name)
    for identifier, revision in (
        (retired.id, retired.revision),
        (active.id, active.revision + 1),
        (DefinitionId(value="missing"), 1),
    ):
        ref = PinnedDefinitionReference(
            model=archive.model_version,
            definition_id=identifier,
            definition_revision=revision,
        )
        body = ConceptDefinition(
            attributes=[AttributeDefinition.reference(name="source", target=ref)],
        )
        with pytest.raises(InvalidDecisionError) as single:
            _ = await local.propose_definition(
                actor="author",
                name="invalid",
                meaning="An unresolved target.",
                body=body,
                reason="Inspect the pinned target.",
            )
        assert single.value.issues[0].code == "unresolved_shape_reference"

        builder = DomainModelBuilder(model_info=local.info)
        _ = builder.add_concept(
            name="invalid",
            meaning="An unresolved target.",
            attributes=body.attributes,
        )
        with pytest.raises(InvalidDecisionError) as grouped:
            await _review(
                model=local,
                plan=builder.build_change_plan(reason="Inspect the grouped target."),
            )
        assert grouped.value.issues[0].code == "unresolved_shape_reference"
    assert (await project.get_model(name="consumer")).info.revision == local.info.revision


async def _prepare_upgrade(
    *,
    model: Model,
    change: DependencyChangeIntent,
    reason: str,
) -> ReviewCase:
    builder = DomainModelBuilder(model_info=model.info)
    builder.change_dependencies(change=change)
    return await model.propose_change_plan(
        actor="author",
        plan=builder.build_change_plan(reason=reason),
    )


async def test_reviewed_upgrade_atomically_repairs_a_qualified_reference(tmp_path: Path) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="recruitment",
    )
    shared = await _authored_model(project=project, name="shared")
    earlier = await _publish(model=shared, version="1.0.0")
    later = await _publish(model=shared, version="1.1.0")
    old = earlier.get_concept(name="legal-resource")
    new = later.get_concept(name=old.name)
    before = PinnedDefinitionReference(
        model=earlier.model_version,
        definition_id=old.id,
        definition_revision=old.revision,
    )
    after = PinnedDefinitionReference(
        model=later.model_version,
        definition_id=new.id,
        definition_revision=new.revision,
    )
    model = await project.create_model(
        actor="author",
        name="consumer",
        kind=ModelKind.PROPOSED,
        description="A recruitment model with an external source.",
        dependencies=[earlier.model_version],
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_concept(
        name="recruitment-source",
        meaning="Reference to the applicable legal resource.",
        attributes=[AttributeDefinition.reference(name="resource", target=before)],
    )
    await _review(model=model, plan=builder.build_change_plan(reason="Review the resource link."))
    previous = await _publish(model=model, version="1.0.0")
    stale_preparation = await model.prepare_publication(actor="editor")
    model = await project.get_model(name=model.info.name)
    change = DependencyChangeIntent(
        before=[earlier.model_version],
        after=[later.model_version],
        remappings=[DependencyRemapping(before=before, after=after)],
    )
    case = await _prepare_upgrade(model=model, change=change, reason="Upgrade the declared source.")
    decision = Accept(reason=case.reason)
    preview = await model.preview_changes(case=case, decision=decision)
    assert preview.changes.before_dependencies == change.before
    assert preview.changes.after_dependencies == change.after
    assert not preview.blockers
    assert len(preview.definition_changes) == 1
    assert (await project.get_model(name=model.info.name)).info.dependencies == change.before
    receipt = await model.decide_review(actor="reviewer", case=case, decision=decision)
    reopened = await project.get_model(name=model.info.name)
    assert reopened.info.dependencies == change.after
    await _assert_upgrade_stales_preparation(model=reopened, preparation=stale_preparation)
    concept = await reopened.get_concept(name="recruitment-source")
    archived = previous.get_concept(name=concept.name)
    assert concept.id == archived.id
    assert concept.get_attribute(name="resource").value_type == ConceptReferenceType(concept=after)
    assert (await reopened.get_version(version="1.0.0")).serialize() == previous.serialize()
    record = (await reopened.get_review_history(case_id=case.id)).items[0]
    assert record.id == receipt.decision_id
    assert record.dependency_change is not None
    assert record.dependency_change.before_bundles == (earlier,)
    assert record.dependency_change.after_bundles == (later,)
    updated = await _publish(model=reopened, version="1.1.0")
    portable = DomainModelBundle.deserialize(payload=updated.serialize())
    assert portable.publication.candidate.dependency_bundles == (later,)
    assert any(
        item.dependency_change == record.dependency_change
        for item in portable.publication.candidate.decisions
    )


async def _assert_upgrade_stales_preparation(*, model: Model, preparation: Publication) -> None:
    with pytest.raises(StaleStateError):
        _ = await model.publish(
            publication=preparation,
            version="stale",
            actor="owner",
            reason="A preparation captured before the reviewed transition.",
        )


async def test_blocked_transition_and_stale_acceptance_leave_selection_intact(
    tmp_path: Path,
) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="recruitment",
    )
    upstream = await _authored_model(project=project, name="shared")
    old = await _publish(model=upstream, version="1.0.0")
    new = await _publish(model=upstream, version="1.1.0")
    definition = old.get_concept(name="legal-resource")
    source = PinnedDefinitionReference(
        model=old.model_version,
        definition_id=definition.id,
        definition_revision=definition.revision,
    )
    model = await project.create_model(
        actor="author",
        name="consumer",
        kind=ModelKind.PROPOSED,
        description="An exact reference.",
        dependencies=[old.model_version],
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_concept(
        name="consumer",
        meaning="A reference to the selected meaning.",
        attributes=[AttributeDefinition.reference(name="source", target=source)],
    )
    await _review(
        model=model, plan=builder.build_change_plan(reason="Review the original meaning.")
    )
    model = await project.get_model(name=model.info.name)
    blocked = await _prepare_upgrade(
        model=model,
        change=DependencyChangeIntent(before=[old.model_version], after=[new.model_version]),
        reason="Inspect switching to the new release.",
    )
    accept = Accept(reason="Use the new release.")
    impact = await model.preview_changes(case=blocked, decision=accept)
    assert tuple(item.code for item in impact.blockers) == ("unresolved_shape_reference",)
    with pytest.raises(InvalidDecisionError):
        _ = await model.decide_review(actor="reviewer", case=blocked, decision=accept)
    reject = Reject(reason="Repair the reference in the same transition.")
    _ = await model.decide_review(actor="reviewer", case=blocked, decision=reject)
    model = await project.get_model(name=model.info.name)
    assert model.info.dependencies == (old.model_version,)

    repaired = await _prepare_upgrade(
        model=model,
        change=DependencyChangeIntent(
            before=[old.model_version],
            after=[new.model_version],
            remappings=[
                DependencyRemapping(
                    before=source,
                    after=replace(source, model=new.model_version),
                )
            ],
        ),
        reason="Review the exact repair.",
    )
    await _reject_stale_transition(project=project, model=model, case=repaired, source=source)
    assert (await project.get_model(name=model.info.name)).info.dependencies == (old.model_version,)


async def _reject_stale_transition(
    *,
    project: Project,
    model: Model,
    case: ReviewCase,
    source: PinnedDefinitionReference,
) -> None:
    (member_id,) = case.generated_member_case_ids
    member = await model.get_review_case(case_id=member_id)
    accept = Accept(reason="Apply the inspected adjustment.")
    with pytest.raises(InvalidDecisionError):
        _ = await model.decide_review(actor="reviewer", case=member, decision=accept)
    current = await project.get_model(name=model.info.name)
    edit = DomainModelBuilder(model_info=current.info)
    _ = edit.add_concept(name="new-local-concept", meaning="An independently reviewed fact.")
    await _review(model=current, plan=edit.build_change_plan(reason="Review another local fact."))
    with pytest.raises(StaleStateError):
        _ = await model.decide_review(actor="reviewer", case=case, decision=accept)
    _ = await model.decide_review(
        actor="reviewer",
        case=case,
        decision=Reject(reason="Reload the changed workspace."),
    )
    resolved = await model.get_review_case(case_id=member_id)
    assert resolved.status is CaseStatus.RESOLVED
    recorded = (await model.get_review_history(case_id=member_id)).items[0]
    assert isinstance(recorded.action, Reject)
    assert not recorded.applied_changes.changes
    unchanged = await model.get_concept(name="consumer")
    assert unchanged.get_attribute(name="source").value_type == ConceptReferenceType(concept=source)


async def test_reference_free_dependency_only_plan_requires_parent_acceptance(
    tmp_path: Path,
) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="recruitment",
    )
    shared = await _authored_model(project=project, name="shared")
    version = await _publish(model=shared, version="1.0.0")
    model = await _authored_model(project=project, name="consumer")
    model = await project.get_model(name=model.info.name)
    change = DependencyChangeIntent(before=[], after=[version.model_version])
    case = await _prepare_upgrade(model=model, change=change, reason="Select a shared vocabulary.")
    assert not case.members
    assert not (await project.get_model(name=model.info.name)).info.dependencies
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=case.reason))
    assert (await project.get_model(name=model.info.name)).info.dependencies == change.after
