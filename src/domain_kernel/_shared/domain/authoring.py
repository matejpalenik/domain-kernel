"""Immutable submitted intent for connected model authoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from domain_kernel._shared.domain.definitions import Definition
from domain_kernel._shared.domain.model_values import Terminology
from domain_kernel._shared.domain.naming import require_lookup_name
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.review.domain.decisions import Accept, EditDefinition, Reject
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.contracts import ModelScope
from domain_kernel.shared.validation import (
    is_non_string_sequence,
    require_exact,
    require_text,
    snapshot_sequence,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.definitions import DefinitionBody
    from domain_kernel.review.domain.decisions import ReviewAction


@dataclass(frozen=True, kw_only=True)
class AuthoredContent:
    """Complete explicit content for a proposed definition."""

    name: str
    display_name: str
    meaning: str
    body: DefinitionBody
    aliases: Sequence[str] = ()
    terminology: Terminology = field(default_factory=Terminology)

    def __post_init__(self) -> None:
        """Validate exact names and detach descriptive metadata."""
        require_lookup_name(name=self.name)
        require_text(value=self.display_name, field="Display name")
        require_text(value=self.meaning, field="Meaning")
        require_exact(value=self.terminology, expected=Terminology, field="Terminology")
        object.__setattr__(
            self,
            "aliases",
            snapshot_sequence(items=self.aliases, item_type=str, field="Aliases"),
        )


@dataclass(frozen=True, kw_only=True)
class CreateDefinition:
    """Reserve a locally authored identity when the plan is submitted."""

    definition_id: DefinitionId
    content: AuthoredContent
    reason: str
    kind: Literal["create_definition"] = "create_definition"

    def __post_init__(self) -> None:
        """Require exact nominal identity, content and action."""
        require_exact(value=self.definition_id, expected=DefinitionId, field="Definition identity")
        require_exact(value=self.content, expected=AuthoredContent, field="Authored content")
        require_text(value=self.reason, field="Creation reason")
        require_exact(value=self.kind, expected=str, field="Plan action kind")
        if self.kind != "create_definition":
            raise ValueError("Use the create definition operation kind")

    def draft(self, *, scope: ModelScope) -> Definition:
        """Return the pending definition in the plan's model scope."""
        content = self.content
        return Definition(
            id=self.definition_id,
            scope=scope,
            revision=1,
            name=content.name,
            display_name=content.display_name,
            meaning=content.meaning,
            body=content.body,
            aliases=content.aliases,
            terminology=content.terminology,
            rationale=self.reason,
        )


@dataclass(frozen=True, kw_only=True)
class IncludeCase:
    """Evaluate an inspected case with an explicit action inside a plan."""

    case_id: ReviewCaseId
    expected_version: int
    decision: ReviewAction
    kind: Literal["include_case"] = "include_case"

    def __post_init__(self) -> None:
        """Validate the inspected version and one applicable leaf action."""
        require_exact(value=self.case_id, expected=ReviewCaseId, field="Case identity")
        require_exact(value=self.expected_version, expected=int, field="Case version")
        if self.expected_version < 1:
            raise ValueError("Case version must be positive")
        if type(self.decision) not in (Accept, EditDefinition, Reject):
            raise TypeError("Choose an explicit leaf decision")
        require_exact(value=self.kind, expected=str, field="Plan action kind")
        if self.kind != "include_case":
            raise ValueError("Use the include case operation kind")


type PlannedOperation = CreateDefinition | IncludeCase


@dataclass(frozen=True, kw_only=True)
class ModelChangePlan:
    """Detached authoring intent guarded by an inspected workspace revision."""

    id: ChangePlanId
    scope: ModelScope
    expected_workspace_revision: int
    reason: str
    bindings: Sequence[Definition]
    operations: Sequence[PlannedOperation]

    def __post_init__(self) -> None:
        """Reject overlapping targets and foreign inspected bindings."""
        require_exact(value=self.id, expected=ChangePlanId, field="Plan identity")
        require_exact(value=self.scope, expected=ModelScope, field="Plan scope")
        require_exact(
            value=self.expected_workspace_revision, expected=int, field="Workspace revision"
        )
        require_text(value=self.reason, field="Plan reason")
        if self.expected_workspace_revision < 0:
            raise ValueError("Workspace revision must be nonnegative")
        bindings = snapshot_sequence(
            items=self.bindings, item_type=Definition, field="Plan bindings"
        )
        if any(binding.scope != self.scope for binding in bindings):
            raise ValueError("Use inspected bindings from the same model scope")
        if len({binding.id for binding in bindings}) != len(bindings):
            raise ValueError("Use one inspected snapshot for each bound definition")
        if not is_non_string_sequence(self.operations) or not self.operations:
            raise ValueError("A change plan needs at least one authored operation")
        operations = tuple(self.operations)
        if any(type(operation) not in (CreateDefinition, IncludeCase) for operation in operations):
            raise TypeError("Use supported manual plan operations")
        additions = tuple(
            operation for operation in operations if isinstance(operation, CreateDefinition)
        )
        cases = tuple(
            operation.case_id for operation in operations if isinstance(operation, IncludeCase)
        )
        if (
            len({operation.definition_id for operation in additions}) != len(additions)
            or len({operation.content.name for operation in additions}) != len(additions)
            or len(set(cases)) != len(cases)
            or {binding.id for binding in bindings}
            & {operation.definition_id for operation in additions}
        ):
            raise ValueError("Use distinct identities, lookup names and cases in a change plan")
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "operations", operations)
