"""One explicitly reviewed change of qualified target."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.contracts import PinnedDefinitionReference
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


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
