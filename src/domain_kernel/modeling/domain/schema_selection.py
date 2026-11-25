"""Resolve schema selections against exact released definitions and typed edges."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from domain_kernel.modeling.domain.dependencies import dependency_closure
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.definition_errors import (
    DefinitionKindMismatchError,
    DefinitionNotFoundError,
)
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.interchange import UnitAnnotation, UnitBindingAnnotation
from domain_kernel.shared.contracts import PinnedDefinitionReference
from domain_kernel.shared.domain.business_decisions import RuleDefinition
from domain_kernel.shared.domain.data_shapes import ConstraintLanguage
from domain_kernel.shared.domain.definitions import (
    Concept,
    ConceptDefinition,
    Definition,
    RelationshipDefinition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
    typed_definition,
)
from domain_kernel.shared.domain.semantic_definitions import SemanticLinkDefinition
from domain_kernel.shared.domain.shape_graph import shape_references
from domain_kernel.shared.errors import ResourceLimitError, ScopeMismatchError, StaleStateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.interchange import JsonSchemaProjectionRequest
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle
    from domain_kernel.shared.contracts import DefinitionReference, ModelVersion

_MAX_SELECTED = 10_000


@dataclass(frozen=True, kw_only=True)
class SelectedDefinition:
    """One exact definition bound to its published owner."""

    pin: PinnedDefinitionReference
    definition: Definition


@final
class PublishedShapes:
    """Index active definitions and resolve typed edges without workspace access."""

    def __init__(self, *, bundle: DomainModelBundle) -> None:
        """Index active definitions and their related reviewed semantics."""
        self.model = bundle.model_version
        archives = dependency_closure(
            scope=bundle.scope, bundles=bundle.publication.candidate.dependency_bundles
        )
        self._index = {
            (archive.model_version, item.id): SelectedDefinition(
                pin=PinnedDefinitionReference(
                    model=archive.model_version,
                    definition_id=item.id,
                    definition_revision=item.revision,
                ),
                definition=item,
            )
            for archive in (bundle, *archives)
            for item in archive.content.definitions
            if item.status is DefinitionStatus.APPROVED
        }
        adjacent: dict[
            tuple[ModelVersion, PinnedDefinitionReference], list[SelectedDefinition]
        ] = {}
        constraints: dict[ModelVersion, list[SelectedDefinition]] = {}
        for item in self._index.values():
            body = item.definition.body
            if isinstance(body, (RelationshipDefinition, SemanticLinkDefinition)):
                for edge in shape_references(body=body):
                    other = self.resolve(owner=item.pin.model, reference=edge.target)
                    adjacent.setdefault((item.pin.model, other.pin), []).append(item)
            elif isinstance(body, RuleDefinition) and any(
                constraint.language is not ConstraintLanguage.TEXT
                for constraint in body.constraints
            ):
                constraints.setdefault(item.pin.model, []).append(item)
        self._adjacent = adjacent
        self._constraints = constraints

    def resolve(self, *, owner: ModelVersion, reference: DefinitionReference) -> SelectedDefinition:
        """Resolve a relative local ID or verify every component of a supplied pin."""
        if isinstance(reference, PinnedDefinitionReference):
            match = self._index.get((reference.model, reference.definition_id))
            if match is None:
                raise DefinitionNotFoundError
            if match.pin != reference:
                raise StaleStateError(message="Use the exact active revision from the publication.")
            return match
        if isinstance(reference, DefinitionId):
            match = self._index.get((owner, reference))
            if match is not None:
                return match
        raise DefinitionNotFoundError

    def root(self, *, request: JsonSchemaProjectionRequest) -> SelectedDefinition:
        """Bind an inspected root to the exact active local snapshot or dependency pin."""
        reference = request.root
        if not isinstance(reference, Definition):
            selected = self.resolve(owner=self.model, reference=reference)
            _require_root_kind(definition=selected.definition)
            return selected
        if reference.scope != self.model.scope:
            raise ScopeMismatchError
        selected = self.resolve(owner=self.model, reference=reference.id)
        _require_root_kind(definition=selected.definition)
        original = selected.definition
        expected = (
            typed_definition(value=original, body_type=ConceptDefinition, view_type=Concept)
            if isinstance(reference, Concept)
            else original
        )
        if reference != expected:
            raise StaleStateError(
                message="Select the unmodified definition from the exact release."
            )
        return selected

    def closure(
        self, *, roots: Sequence[SelectedDefinition], include_model_semantics: bool
    ) -> tuple[SelectedDefinition, ...]:
        """Retain every reachable field, relationship, lexical vocabulary and unit."""
        queue = deque(roots)
        selected: dict[PinnedDefinitionReference, SelectedDefinition] = {}
        while queue:
            item = queue.popleft()
            owner = item.pin.model
            if item.pin in selected:
                continue
            if len(selected) >= _MAX_SELECTED:
                raise ResourceLimitError(message="Select a smaller released shape closure.")
            selected[item.pin] = item
            queue.extend(
                self.resolve(owner=owner, reference=edge.target)
                for edge in shape_references(body=item.definition.body)
            )
            if include_model_semantics and isinstance(item.definition.body, ConceptDefinition):
                queue.extend(self._adjacent.get((owner, item.pin), ()))
            if include_model_semantics and isinstance(
                item.definition.body, (ConceptDefinition, StructuredValueDefinition)
            ):
                queue.extend(self._constraints.get(owner, ()))
        return tuple(
            sorted(
                selected.values(),
                key=lambda item: (
                    item.pin.model.scope.model_id.value,
                    item.pin.definition_id.value,
                ),
            )
        )

    def related(self, *, item: SelectedDefinition) -> Sequence[SelectedDefinition]:
        """Find relationships whose participation constrains this exact owner."""
        return self._adjacent.get((item.pin.model, item.pin), ())

    def local_selection(
        self, *, definition_ids: Sequence[DefinitionId] | None
    ) -> tuple[SelectedDefinition, ...]:
        """Select explicit local definition IDs or all active local definitions."""
        if definition_ids is None:
            return tuple(item for item in self._index.values() if item.pin.model == self.model)
        return tuple(self.resolve(owner=self.model, reference=item) for item in definition_ids)

    def units(
        self, *, selected: Sequence[SelectedDefinition]
    ) -> tuple[tuple[UnitAnnotation, ...], tuple[UnitBindingAnnotation, ...]]:
        """Capture shared unit definitions and every exact member-to-unit edge."""
        units: list[UnitAnnotation] = []
        bindings: list[UnitBindingAnnotation] = []
        for item in selected:
            definition, body = item.definition, item.definition.body
            if isinstance(body, UnitDefinition):
                units.append(
                    UnitAnnotation(
                        source=item.pin,
                        name=definition.name,
                        display_name=definition.display_name,
                        meaning=definition.meaning,
                        aliases=definition.aliases,
                        terminology=definition.terminology,
                        body=body,
                    )
                )
            elif isinstance(body, ValueSetDefinition):
                bindings.extend(
                    UnitBindingAnnotation(
                        source=item.pin,
                        code=member.code,
                        unit=self.resolve(owner=item.pin.model, reference=member.unit).pin,
                    )
                    for member in body.members
                    if member.unit is not None
                )
        return tuple(units), tuple(bindings)


def _require_root_kind(*, definition: Definition) -> None:
    if not isinstance(definition.body, (ConceptDefinition, StructuredValueDefinition)):
        raise DefinitionKindMismatchError
