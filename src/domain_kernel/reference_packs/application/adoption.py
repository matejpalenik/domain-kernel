"""Build a guarded local graph from an exact explicitly selected pattern."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from domain_kernel._shared.domain.authoring import (
    AuthoredContent,
    CreateDefinition,
    ModelChangePlan,
)
from domain_kernel._shared.domain.local_children import copy_shape_bodies
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.definition_errors import (
    DefinitionAlreadyExistsError,
    DefinitionNotFoundError,
)
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.contracts import (
    DefinitionBinding,
    Pattern,
    PatternAdoption,
)
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.shared.contracts import DefinitionReference, Issue
from domain_kernel.shared.errors import (
    InvalidReferencePackError,
    MissingCapabilityError,
    PatternNotFoundError,
    ScopeMismatchError,
    StaleStateError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
        ReferenceDefinitionId,
    )
    from domain_kernel.review.application.ports import DefinitionRepository
    from domain_kernel.shared.contracts import ModelScope


def _bad_pattern(*, code: str, message: str) -> InvalidReferencePackError:
    return InvalidReferencePackError(issues=(Issue(code=code, path=("pattern",), message=message),))


def inspect_pattern(*, pack: ReferencePack | None, requested: Pattern) -> Pattern:
    """Require the exact materialized pack and the full inspected pattern."""
    if pack is None:
        raise MissingCapabilityError(message="Create the workspace with a selected reference pack")
    if requested.reference_pack != pack.pin:
        raise ScopeMismatchError
    try:
        stored = pack.get_pattern(pattern_id=requested.id)
    except PatternNotFoundError:
        raise _bad_pattern(
            code="unknown_pattern", message="Select a pattern in the exact pack."
        ) from None
    if stored != requested:
        raise _bad_pattern(code="modified_pattern", message="Inspect the exact stored pattern.")
    return stored


async def _inspect_bindings(
    *,
    scope: ModelScope,
    pattern: Pattern,
    bindings: Sequence[DefinitionBinding],
    repository: DefinitionRepository,
) -> dict[ReferenceDefinitionId, Definition]:
    sources = {item.id: item for item in pattern.definitions}
    if (
        len({item.reference_id for item in bindings}) != len(bindings)
        or len({item.definition_id for item in bindings}) != len(bindings)
        or not {item.reference_id for item in bindings} <= sources.keys()
    ):
        raise _bad_pattern(
            code="invalid_binding", message="Bind each selected pattern member once."
        )
    seen: dict[ReferenceDefinitionId, Definition] = {}
    for binding in bindings:
        stored = await repository.get(
            scope=scope,
            name=None,
            definition_id=binding.definition_id,
            revision=None,
        )
        if (
            stored.revision != binding.definition_revision
            or stored.status is not DefinitionStatus.APPROVED
        ):
            raise StaleStateError(message="Inspect the current approved binding revision")
        if stored.kind is not sources[binding.reference_id].body.kind:
            raise _bad_pattern(
                code="binding_kind",
                message="Bind a local definition with the same declared kind.",
            )
        seen[binding.reference_id] = stored
    return seen


async def build_adoption_plan(  # noqa: PLR0913 - Explicit verified graph and local revision guards.
    *,
    scope: ModelScope,
    revision: int,
    pattern: Pattern,
    bindings: Sequence[DefinitionBinding],
    repository: DefinitionRepository,
    reason: str,
) -> ModelChangePlan:
    """Create local IDs and rewrite typed references inside the proposal transaction."""
    if pattern.reference_pack is None:
        raise ScopeMismatchError
    reused = await _inspect_bindings(
        scope=scope,
        pattern=pattern,
        bindings=bindings,
        repository=repository,
    )
    for item in pattern.definitions:
        if item.id in reused:
            continue
        try:
            _ = await repository.get(scope=scope, name=item.name, definition_id=None, revision=None)
        except DefinitionNotFoundError:
            continue
        raise DefinitionAlreadyExistsError
    targets = {
        item.id: reused[item.id].id if item.id in reused else DefinitionId(value=uuid4().hex)
        for item in pattern.definitions
    }
    replacements = dict[DefinitionReference, DefinitionReference](targets.items())
    bodies = copy_shape_bodies(
        bodies={item.id: item.body for item in pattern.definitions},
        replacements=replacements,
        existing={identity: definition.body for identity, definition in reused.items()},
    )
    operations = tuple(
        CreateDefinition(
            definition_id=targets[item.id],
            reason=reason,
            content=AuthoredContent(
                name=item.name,
                display_name=item.name,
                meaning=item.meaning,
                body=bodies[item.id],
                terminology=item.terminology,
            ),
        )
        for item in pattern.definitions
        if item.id not in reused
    )
    return ModelChangePlan(
        id=ChangePlanId(value=uuid4().hex),
        scope=scope,
        expected_workspace_revision=revision,
        reason=reason,
        operations=operations,
        bindings=tuple(reused.values()),
        pattern_adoption=PatternAdoption(
            reference_pack=pattern.reference_pack,
            pattern=pattern,
            definitions=[
                DefinitionBinding(
                    reference_id=item.id,
                    definition_id=targets[item.id],
                    definition_revision=reused[item.id].revision if item.id in reused else 1,
                )
                for item in pattern.definitions
            ],
        ),
    )
