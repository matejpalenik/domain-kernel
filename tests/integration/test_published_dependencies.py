"""Exercise exact published references through creation, review and portable consumption."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AttributeDefinition,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    ConceptReferenceType,
    DefinitionId,
    DomainModelBuilder,
    DomainModelBundle,
    InvalidDecisionError,
    ModelKind,
    PinnedDefinitionReference,
    PublicationNotFoundError,
    ScopeMismatchError,
)
from domain_kernel.modeling.domain.dependencies import dependency_closure
from domain_kernel.shared.errors import InvalidBundleError
from domain_kernel.shared.hashing import hash_bytes

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import Model, ModelChangePlan, ModelVersion, Project

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
            dependencies=(replace(pin, content_hash=hash_bytes(content=b"substitution")),),
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
