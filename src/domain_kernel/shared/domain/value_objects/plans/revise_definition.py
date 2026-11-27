"""Propose a full revision of an inspected active definition."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.shared.domain.value_objects.authored_content import AuthoredContent
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.entities.definition import Definition


@dataclass(frozen=True, kw_only=True)
class ReviseDefinition:
    """Propose a full revision of an inspected active definition."""

    before: Definition
    content: AuthoredContent
    reason: str
    kind: Literal["revise_definition"] = "revise_definition"

    def __post_init__(self) -> None:
        """Keep identity, lookup name and kind stable across content revisions."""
        TextValidation.require_text(value=self.reason, field="Revision reason")
        RuntimeTypeValidation.require_exact(
            value=self.content, expected=AuthoredContent, field="Revised content"
        )

        if self.before.status is not DefinitionStatus.APPROVED or self.kind != "revise_definition":
            raise ValueError("Revise an inspected active definition")

        if self.content.name != self.before.name or self.content.body.kind is not self.before.kind:
            raise ValueError("A revision preserves its definition name and kind")

        if self.content == AuthoredContent(
            name=self.before.name,
            display_name=self.before.display_name,
            meaning=self.before.meaning,
            body=self.before.body,
            aliases=self.before.aliases,
            terminology=self.before.terminology,
            schema_origins=self.before.schema_origins,
        ):
            raise ValueError("Change the definition before proposing a revision")

    def draft(self) -> Definition:
        """Build the full replacement at the next version of this identity."""
        return replace(
            self.before,
            revision=self.before.revision + 1,
            status=DefinitionStatus.PROPOSED,
            display_name=self.content.display_name,
            meaning=self.content.meaning,
            body=self.content.body,
            aliases=self.content.aliases,
            terminology=self.content.terminology,
            schema_origins=self.content.schema_origins or self.before.schema_origins,
            rationale=self.reason,
        )
