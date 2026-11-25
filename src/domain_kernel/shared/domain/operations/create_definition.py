"""Reserve a locally authored identity when the plan is submitted."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.domain.entities.definition import Definition
from domain_kernel.shared.domain.value_objects.authored_content import AuthoredContent
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.shared.contracts import ModelScope


@dataclass(frozen=True, kw_only=True)
class CreateDefinition:
    """Reserve a locally authored identity when the plan is submitted."""

    definition_id: DefinitionId
    content: AuthoredContent
    reason: str
    kind: Literal["create_definition"] = "create_definition"

    def __post_init__(self) -> None:
        """Require exact nominal identity, content and action."""
        RuntimeTypeValidation.require_exact(
            value=self.definition_id, expected=DefinitionId, field="Definition identity"
        )
        RuntimeTypeValidation.require_exact(
            value=self.content, expected=AuthoredContent, field="Authored content"
        )
        TextValidation.require_text(value=self.reason, field="Creation reason")
        RuntimeTypeValidation.require_exact(value=self.kind, expected=str, field="Plan action kind")
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
            schema_origins=content.schema_origins,
            rationale=self.reason,
        )
