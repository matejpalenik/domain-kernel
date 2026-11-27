"""Prospective effects for the model definition lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.policies.shape_graph_validation_policy import (
    ShapeGraphValidationPolicy,
)
from domain_kernel.shared.domain.value_objects.definition_change import DefinitionChange

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
    from domain_kernel.shared.domain.value_objects.ontology_closure import OntologyClosure
    from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
        PinnedDefinitionReference,
    )


@final
class DefinitionLifecyclePolicy:
    """Describe and check transitions between definition revisions."""

    @staticmethod
    def definition_change(*, before: Definition | None, after: Definition) -> DefinitionChange:
        """Capture a created, revised or retired definition without applying it."""
        if before is None:
            kind = DefinitionChangeKind.ADD
        elif after.status is DefinitionStatus.RETIRED:
            kind = DefinitionChangeKind.RETIRE
        else:
            kind = DefinitionChangeKind.EDIT

        return DefinitionChange(
            kind=kind, before=() if before is None else (before,), after=(after,)
        )

    @staticmethod
    def check_definition_changes(
        *,
        scope: ModelScope,
        active: Sequence[Definition],
        changes: Sequence[DefinitionChange],
        dependencies: Mapping[PinnedDefinitionReference, Definition] | None = None,
        ontologies: Sequence[OntologyClosure] = (),
    ) -> tuple[Issue, ...]:
        """Check exact replacements and the combined active graph before applying a transition."""
        prospective = {value.id: value for value in active}
        writes: set[DefinitionId] = set()
        revised = [value for change in changes for value in change.after]
        problems: list[Issue] = []

        for value in revised:
            if value.id in writes:
                problems.append(
                    Issue(
                        code="contradictory_changes",
                        path=("definitions", value.id.value),
                        message="Apply at most one inspected change per definition",
                    )
                )
            else:
                prospective[value.id] = value
                writes.add(value.id)

        if len({item.name for item in prospective.values()}) != len(prospective):
            problems.append(
                Issue(
                    code="duplicate_definition_name",
                    path=("definitions",),
                    message="Choose a distinct lookup name for each active identity",
                )
            )

        for item in revised:
            if item.status is not DefinitionStatus.RETIRED:
                continue
            for replacement_id in item.replacement_ids:
                replacement = prospective.get(replacement_id)
                if (
                    replacement is None
                    or replacement.status is not DefinitionStatus.APPROVED
                    or replacement.kind is not item.kind
                ):
                    problems.append(
                        Issue(
                            code="invalid_replacement",
                            path=("definitions", item.id.value, "replacement_ids"),
                            message="Select an active replacement of the same definition kind",
                        )
                    )

        return (
            *problems,
            *ShapeGraphValidationPolicy.validate_model_shapes(
                scope=scope,
                definitions=tuple(prospective.values()),
                dependencies=dependencies,
                ontologies=ontologies,
            ),
        )
