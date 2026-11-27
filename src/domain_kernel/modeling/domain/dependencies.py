"""Exact transitive closure over explicitly supplied published models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.invalid_bundle_error import InvalidBundleError
from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.snapshots import DomainModelBundle
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
    from domain_kernel.shared.domain.value_objects.model_version import ModelVersion

_MAX_DEPENDENCY_DEPTH = 16


def _invalid(*, code: str, message: str) -> InvalidBundleError:
    return InvalidBundleError(
        issues=(Issue(code=code, path=("dependencies",), message=message),),
    )


def dependency_closure(
    *,
    scope: ModelScope,
    bundles: Sequence[DomainModelBundle],
) -> tuple[DomainModelBundle, ...]:
    """Collect each exact published dependency once and check compatible routes."""
    selected: dict[ModelScope, DomainModelBundle] = {}
    heights: dict[ModelVersion, int] = {}

    def visit(*, bundle: DomainModelBundle, ancestors: frozenset[ModelScope]) -> int:
        pin = bundle.model_version
        depth = len(ancestors)
        if pin.scope.project_id != scope.project_id:
            raise _invalid(
                code="dependency_project",
                message="Select a published dependency in this project.",
            )
        if pin.scope in ancestors:
            raise _invalid(
                code="dependency_cycle",
                message="Remove the dependency route back to an ancestor model.",
            )
        if depth > _MAX_DEPENDENCY_DEPTH:
            raise _invalid(
                code="dependency_depth",
                message="Limit each route to 16 levels of published dependencies.",
            )
        existing = selected.get(pin.scope)
        if existing is not None and existing != bundle:
            raise _invalid(
                code="dependency_conflict",
                message="Select one identical published pin and bundle per dependency model.",
            )
        selected[pin.scope] = bundle
        if pin not in heights:
            heights[pin] = visit_children(
                children=bundle.publication.candidate.dependency_bundles,
                ancestors=ancestors | {pin.scope},
            )
        height = heights[pin]
        if depth + height > _MAX_DEPENDENCY_DEPTH:
            raise _invalid(
                code="dependency_depth",
                message="Limit each route to 16 levels of published dependencies.",
            )
        return height

    def visit_children(
        *, children: Sequence[DomainModelBundle], ancestors: frozenset[ModelScope]
    ) -> int:
        if len({item.scope for item in children}) != len(children):
            raise _invalid(
                code="dependency_duplicate",
                message="Declare each direct dependency once.",
            )
        return max((1 + visit(bundle=item, ancestors=ancestors) for item in children), default=0)

    _ = visit_children(children=bundles, ancestors=frozenset({scope}))
    return tuple(selected.values())


def dependency_definitions(
    *,
    scope: ModelScope,
    bundles: Sequence[DomainModelBundle],
) -> dict[PinnedDefinitionReference, Definition]:
    """Index approved definitions only, retaining model, version and revision identities."""
    return {
        PinnedDefinitionReference(
            model=bundle.model_version,
            definition_id=definition.id,
            definition_revision=definition.revision,
        ): definition
        for bundle in dependency_closure(scope=scope, bundles=bundles)
        for definition in bundle.content.definitions
        if definition.status is DefinitionStatus.APPROVED
    }
