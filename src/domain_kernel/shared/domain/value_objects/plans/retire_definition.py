"""Propose a retained tombstone and exact selected replacement IDs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.entities.definition import Definition


@dataclass(frozen=True, kw_only=True)
class RetireDefinition:
    """Propose a retained tombstone and exact selected replacement IDs."""

    before: Definition
    replacement_ids: Sequence[DefinitionId]
    reason: str
    kind: Literal["retire_definition"] = "retire_definition"

    def __post_init__(self) -> None:
        """Capture distinct replacements apart from the retired identity."""
        TextValidation.require_text(value=self.reason, field="Retirement reason")

        if self.before.status is not DefinitionStatus.APPROVED or self.kind != "retire_definition":
            raise ValueError("Retire an inspected active definition")

        replacements = SequenceValidation.snapshot_sequence(
            items=self.replacement_ids,
            item_type=DefinitionId,
            field="Retirement replacements",
        )
        if self.before.id in replacements or len(set(replacements)) != len(replacements):
            raise ValueError("Select distinct replacement identities")

        object.__setattr__(self, "replacement_ids", replacements)

    def draft(self) -> Definition:
        """Prepare an immutable retirement without applying it."""
        return replace(
            self.before,
            revision=self.before.revision + 1,
            status=DefinitionStatus.PROPOSED,
            replacement_ids=self.replacement_ids,
            rationale=self.reason,
        )
