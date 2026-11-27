"""Require the consumer to enforce a pinned relationship."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel.shared.domain.validators.obligation_kind_validation import (
    ObligationKindValidation,
)
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class RelationshipEnforcementObligation:
    """Require the consumer to enforce a pinned relationship."""

    relationship: PinnedDefinitionReference
    kind: Literal["relationship_enforcement"] = "relationship_enforcement"

    def __post_init__(self) -> None:
        """Require the exact typed relationship reference."""
        RuntimeTypeValidation.require_exact(
            value=self.relationship, expected=PinnedDefinitionReference, field="Relationship"
        )

        ObligationKindValidation.require_kind(value=self.kind, expected="relationship_enforcement")
