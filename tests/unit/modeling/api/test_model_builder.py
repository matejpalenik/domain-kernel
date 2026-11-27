from datetime import UTC, datetime

import pytest

from domain_kernel import (
    AttributeDefinition,
    CollectionKind,
    Concept,
    ConceptDefinition,
    Count,
    DefinitionId,
    DefinitionStatus,
    KeyDefinition,
    ModelId,
    ModelInfo,
    ModelKind,
    ModelScope,
    ProjectId,
)
from domain_kernel.authoring import DomainModelBuilder
from domain_kernel.shared.domain.value_objects.plans.revise_definition import ReviseDefinition


def test_build_keeps_ids_and_creates_detached_plan_revisions() -> None:
    builder = DomainModelBuilder(
        model_info=ModelInfo(
            scope=ModelScope(
                project_id=ProjectId(value="project"), model_id=ModelId(value="model")
            ),
            name="observed",
            display_name="Observed",
            kind=ModelKind.OBSERVED,
            description="Existing.",
            created_at=datetime.now(tz=UTC),
            revision=3,
        )
    )
    _ = builder.add_concept(display_name="Machine", meaning="Physical asset.")
    first = builder.build_change_plan(reason="Start the asset vocabulary.")
    assert builder.build_change_plan(reason=first.reason) == first
    renamed_intent = builder.build_change_plan(reason="Propose an asset name for review.")
    assert renamed_intent.id != first.id
    assert renamed_intent.reason != first.reason
    _ = builder.add_concept(display_name="Site", meaning="Physical operating location.")
    second = builder.build_change_plan(reason=first.reason)
    assert second.id != first.id
    assert second.operations[:1] == first.operations


def test_child_edits_coalesce_with_metadata_and_preserve_failed_attempts() -> None:
    info = ModelInfo(
        scope=ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="model")),
        name="observed",
        display_name="Observed",
        kind=ModelKind.OBSERVED,
        description="Existing.",
        created_at=datetime.now(tz=UTC),
        revision=1,
    )
    code = AttributeDefinition.string(name="code", required=True)
    tags = AttributeDefinition.string(
        name="tags",
        collection=CollectionKind.SET,
        min_items=Count(value=1),
        max_items=Count(value=4),
    )
    key = KeyDefinition(name="record-key", attributes=[code.id])
    inspected = Concept(
        id=DefinitionId(value="record"),
        scope=info.scope,
        revision=1,
        name="record",
        display_name="Record",
        meaning="Previous meaning",
        body=ConceptDefinition(attributes=[code, tags], keys=[key]),
        status=DefinitionStatus.APPROVED,
    )
    builder = DomainModelBuilder(model_info=info)
    builder.edit_concept(concept=inspected, meaning="Clarified meaning")
    before = builder.build_change_plan(reason="Refine the same record.")
    with pytest.raises(ValueError, match="maximum"):
        builder.edit_attribute(concept=inspected, attribute=tags, min_items=Count(value=5))
    assert builder.build_change_plan(reason=before.reason) == before
    builder.edit_attribute(concept=inspected, attribute=tags, min_items=None)
    builder.edit_key(concept=inspected, key=key, display_name="Record identity")
    after = builder.build_change_plan(reason=before.reason)
    assert len(after.operations) == 1
    operation = after.operations[0]
    assert isinstance(operation, ReviseDefinition)
    assert operation.content.meaning == "Clarified meaning"
    assert isinstance(operation.content.body, ConceptDefinition)
    updated_tags = operation.content.body.attributes[1]
    assert updated_tags.id == tags.id
    assert updated_tags.min_items == Count(value=0)
    assert updated_tags.max_items == tags.max_items
    assert operation.content.body.keys[0].id == key.id
    assert inspected.get_attribute(name=tags.name) == tags

    with pytest.raises(ValueError, match="original, unmodified attribute"):
        builder.remove_attribute(concept=inspected, attribute=tags)
    assert builder.build_change_plan(reason=after.reason) == after
