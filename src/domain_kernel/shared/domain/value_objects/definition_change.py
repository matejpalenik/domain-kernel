"""Exact revisions on either side of one prospective change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.shared.domain.entities.definition import Definition
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class DefinitionChange:
    """Exact revisions on either side of one prospective change."""

    kind: DefinitionChangeKind
    before: Sequence[Definition]
    after: Sequence[Definition]
    evidence: tuple[()] = ()

    def __post_init__(self) -> None:
        """Detach both sides of the change."""
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=DefinitionChangeKind, field="Definition change kind"
        )

        object.__setattr__(
            self,
            "before",
            SequenceValidation.snapshot_sequence(
                items=self.before, item_type=Definition, field="Before revisions"
            ),
        )
        object.__setattr__(
            self,
            "after",
            SequenceValidation.snapshot_sequence(
                items=self.after, item_type=Definition, field="After revisions"
            ),
        )
