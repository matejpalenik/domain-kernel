"""Explicit intent for changing an exact published dependency selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.contracts import ModelVersion, PinnedDefinitionReference
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class DependencyRemapping:
    """One explicitly reviewed change of qualified target."""

    before: PinnedDefinitionReference
    after: PinnedDefinitionReference

    def __post_init__(self) -> None:
        """Bind two distinct exact definition revisions."""
        RuntimeTypeValidation.require_exact(
            value=self.before, expected=PinnedDefinitionReference, field="Old target"
        )
        RuntimeTypeValidation.require_exact(
            value=self.after, expected=PinnedDefinitionReference, field="New target"
        )
        if self.before == self.after:
            raise ValueError("Select a different exact dependency target")


@dataclass(frozen=True, kw_only=True)
class DependencyChangeRequest:
    """The complete previous and desired selections and their explicit repair edges."""

    before: Sequence[ModelVersion]
    after: Sequence[ModelVersion]
    remappings: Sequence[DependencyRemapping] = ()

    def __post_init__(self) -> None:
        """Detach inputs and require one definite transition."""
        previous = SequenceValidation.snapshot_sequence(
            items=self.before, item_type=ModelVersion, field="Old pins"
        )
        desired = SequenceValidation.snapshot_sequence(
            items=self.after, item_type=ModelVersion, field="New pins"
        )
        if set(previous) == set(desired):
            raise ValueError("Change at least one exact dependency pin")
        for selection in (previous, desired):
            if len({pin.scope for pin in selection}) != len(selection):
                raise ValueError("Select only one direct pin per dependency model")
        remappings = SequenceValidation.snapshot_sequence(
            items=self.remappings,
            item_type=DependencyRemapping,
            field="Dependency remappings",
        )
        if len({item.before for item in remappings}) != len(remappings):
            raise ValueError("Use one explicit remapping for each old target")
        object.__setattr__(self, "before", previous)
        object.__setattr__(self, "after", desired)
        object.__setattr__(self, "remappings", remappings)
