"""Capture reviewed dependency transitions and generate exact local repairs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.dependencies import dependency_definitions
from domain_kernel.modeling.domain.snapshots import DependencyChange
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.shared.domain.authoring import AuthoredContent, ReviseDefinition
from domain_kernel.shared.domain.shape_graph import remap_shape
from domain_kernel.shared.errors import MissingCapabilityError, StaleStateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.application.dependencies import PublishedDependencies
    from domain_kernel.shared.contracts import (
        DefinitionReference,
        ModelScope,
        PinnedDefinitionReference,
    )
    from domain_kernel.shared.domain.authoring import ModelChangePlan
    from domain_kernel.shared.domain.definitions import Definition, DefinitionBody


def _revision(*, item: Definition, body: DefinitionBody, reason: str) -> ReviseDefinition:
    return ReviseDefinition(
        before=item,
        content=AuthoredContent(
            name=item.name,
            display_name=item.display_name,
            meaning=item.meaning,
            body=body,
            aliases=item.aliases,
            terminology=item.terminology,
            schema_origins=item.schema_origins,
        ),
        reason=reason,
    )


async def capture_upgrade(
    *,
    plan: ModelChangePlan,
    active: Sequence[Definition],
    resolver: PublishedDependencies | None,
) -> tuple[DependencyChange | None, tuple[ReviseDefinition, ...]]:
    """Verify the two contexts and generate remaps only on otherwise untouched owners."""
    request = plan.dependency_change
    if request is None:
        return None, ()
    if resolver is None:
        raise MissingCapabilityError(message="Configure access to exact dependency selections")
    current = await resolver.selected(scope=plan.scope)
    if current != request.before:
        raise StaleStateError(message="Reload the inspected dependency selection")
    before = await resolver.materialize(scope=plan.scope, pins=current)
    after = await resolver.materialize(scope=plan.scope, pins=request.after)
    old_index = dependency_definitions(scope=plan.scope, bundles=before)
    new_index = dependency_definitions(scope=plan.scope, bundles=after)
    replacements: dict[DefinitionReference, DefinitionReference] = {}
    for item in request.remappings:
        old = old_index.get(item.before)
        new = new_index.get(item.after)
        if old is None or new is None or old.kind is not new.kind:
            raise InvalidDecisionError(
                message="Remap exact active revisions of the same definition kind",
            )
        replacements[item.before] = item.after
    edited = tuple(item.before.id for item in plan.operations if isinstance(item, ReviseDefinition))
    retired = tuple(item.before.id for item in plan.operations if item.kind == "retire_definition")
    explicit = {*edited, *retired}
    repairs: list[ReviseDefinition] = []
    if replacements:
        for item in active:
            if item.id in explicit:
                continue
            revised = remap_shape(body=item.body, replacements=replacements)
            if revised != item.body:
                repairs.append(_revision(item=item, body=revised, reason=plan.reason))
    return DependencyChange(
        request=request,
        before_bundles=before,
        after_bundles=after,
        affected_definition_ids=(*edited, *retired, *(item.before.id for item in repairs)),
    ), tuple(repairs)


async def inspect_upgrade(
    *,
    scope: ModelScope,
    change: DependencyChange,
    resolver: PublishedDependencies | None,
) -> dict[PinnedDefinitionReference, Definition]:
    """Confirm the exact reserved old and target snapshots before accepting a change."""
    if resolver is None:
        raise MissingCapabilityError(message="Configure access to exact dependency selections")
    current = await resolver.selected(scope=scope)
    if current != change.request.before:
        raise StaleStateError(message="Reload the current dependency selection before accepting")
    old = await resolver.materialize(scope=scope, pins=current)
    target = await resolver.materialize(scope=scope, pins=change.request.after)
    if old != change.before_bundles or target != change.after_bundles:
        raise StaleStateError(
            message="Inspect a new case using the exact published dependency bundles"
        )
    return dependency_definitions(scope=scope, bundles=target)
