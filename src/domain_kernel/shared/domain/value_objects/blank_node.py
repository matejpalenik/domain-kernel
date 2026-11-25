"""A graph name scoped to one pinned document."""

from dataclasses import dataclass
from typing import Literal

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation


@dataclass(frozen=True, kw_only=True)
class BlankNode:
    """A graph name scoped to one pinned document."""

    id: str
    kind: Literal["blank_node"] = "blank_node"

    def __post_init__(self) -> None:
        """Require an exact node identifier and wire tag."""
        TextValidation.require_text(value=self.id, field="Blank node ID")
        RuntimeTypeValidation.require_exact(value=self.kind, expected=str, field="Blank node kind")
        if self.kind != "blank_node":
            raise ValueError("Blank node kind must be 'blank_node'")
