"""The authored intent for a model's dependency change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.value_objects.dependency_remapping import DependencyRemapping
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class DependencyChangeIntent:
    """The current and desired dependency pins and their explicit reference remappings."""

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
