"""Propose the last authored content under a retired identity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.entities.definition import Definition


@dataclass(frozen=True, kw_only=True)
class RestoreDefinition:
    """Propose the last authored content under a retired identity."""

    before: Definition
    reason: str
    kind: Literal["restore_definition"] = "restore_definition"

    def __post_init__(self) -> None:
        """Select a retained tombstone and a new review reason."""
        TextValidation.require_text(value=self.reason, field="Restoration reason")

        if self.before.status is not DefinitionStatus.RETIRED or self.kind != "restore_definition":
            raise ValueError("Restore an inspected retired definition")

    def draft(self) -> Definition:
        """Prepare the next revision with no active replacement lineage."""
        return replace(
            self.before,
            revision=self.before.revision + 1,
            status=DefinitionStatus.PROPOSED,
            replacement_ids=(),
            rationale=self.reason,
        )
