"""Detached authoring intent guarded by an inspected workspace revision."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain_kernel.reference_packs.domain.contracts import PatternAdoption
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.shared.domain.entities.definition import Definition
from domain_kernel.shared.domain.value_objects.dependency_change_intent import (
    DependencyChangeIntent,
)
from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
from domain_kernel.shared.domain.value_objects.plans.correct_mapping import CorrectMapping
from domain_kernel.shared.domain.value_objects.plans.create_definition import CreateDefinition
from domain_kernel.shared.domain.value_objects.plans.include_case import IncludeCase
from domain_kernel.shared.domain.value_objects.plans.restore_definition import RestoreDefinition
from domain_kernel.shared.domain.value_objects.plans.retire_definition import RetireDefinition
from domain_kernel.shared.domain.value_objects.plans.revise_definition import ReviseDefinition
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.types.planned_operation import PlannedOperation


@dataclass(frozen=True, kw_only=True)
class ModelChangePlan:
    """Detached authoring intent guarded by an inspected workspace revision."""

    id: ChangePlanId
    scope: ModelScope
    expected_workspace_revision: int
    reason: str
    bindings: Sequence[Definition]
    operations: Sequence[PlannedOperation]
    pattern_adoption: PatternAdoption | None = None
    dependency_change: DependencyChangeIntent | None = field(
        default=None,
        metadata={"wire_omit_empty": True},
    )

    def __post_init__(self) -> None:
        """Reject overlapping targets and foreign inspected bindings."""
        RuntimeTypeValidation.require_exact(
            value=self.id, expected=ChangePlanId, field="Plan identity"
        )
        RuntimeTypeValidation.require_exact(
            value=self.scope, expected=ModelScope, field="Plan scope"
        )
        RuntimeTypeValidation.require_exact(
            value=self.expected_workspace_revision, expected=int, field="Workspace revision"
        )

        TextValidation.require_text(value=self.reason, field="Plan reason")

        if self.pattern_adoption is not None:
            RuntimeTypeValidation.require_exact(
                value=self.pattern_adoption, expected=PatternAdoption, field="Pattern adoption"
            )

        if self.expected_workspace_revision < 0:
            raise ValueError("Workspace revision must be nonnegative")

        bindings = SequenceValidation.snapshot_sequence(
            items=self.bindings, item_type=Definition, field="Plan bindings"
        )
        if any(binding.scope != self.scope for binding in bindings):
            raise ValueError("Use inspected bindings from the same model scope")
        if len({binding.id for binding in bindings}) != len(bindings):
            raise ValueError("Use one inspected snapshot for each bound definition")

        if not SequenceValidation.is_non_string_sequence(value=self.operations) or (
            not self.operations and self.pattern_adoption is None and self.dependency_change is None
        ):
            raise ValueError("A change plan needs at least one authored operation")
        operations = tuple(self.operations)
        if any(
            type(operation)
            not in (
                CreateDefinition,
                IncludeCase,
                CorrectMapping,
                ReviseDefinition,
                RetireDefinition,
                RestoreDefinition,
            )
            for operation in operations
        ):
            raise TypeError("Use supported manual plan operations")

        self._validate_dependency_operations(operations=operations)

        additions = tuple(
            operation for operation in operations if isinstance(operation, CreateDefinition)
        )
        cases = tuple(
            operation.case_id
            for operation in operations
            if isinstance(operation, (IncludeCase, CorrectMapping))
        )
        revisions = tuple(
            item.before
            for item in operations
            if isinstance(
                item,
                (
                    ReviseDefinition,
                    RetireDefinition,
                    RestoreDefinition,
                ),
            )
        )

        writes = {item.definition_id for item in additions} | {item.id for item in revisions}
        if any(item.scope != self.scope for item in revisions):
            raise ValueError("Use inspected revisions from the same model")
        if (
            len(writes) != len(additions) + len(revisions)
            or len({operation.content.name for operation in additions}) != len(additions)
            or len(set(cases)) != len(cases)
            or {binding.id for binding in bindings}
            & {operation.definition_id for operation in additions}
        ):
            raise ValueError("Use distinct identities, lookup names and cases in a change plan")

        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "operations", operations)

    def _validate_dependency_operations(self, *, operations: Sequence[PlannedOperation]) -> None:
        """Enforce the operations permitted by the requested dependency change."""
        if self.dependency_change is not None:
            RuntimeTypeValidation.require_exact(
                value=self.dependency_change,
                expected=DependencyChangeIntent,
                field="Dependency change",
            )

            if any(
                not isinstance(item, (ReviseDefinition, RetireDefinition)) for item in operations
            ):
                raise ValueError("Dependency plans can only revise or retire existing definitions")

            if self.pattern_adoption is not None:
                raise ValueError("Review dependency changes separately from pattern adoption")
