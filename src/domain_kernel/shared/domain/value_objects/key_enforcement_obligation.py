"""Require the consumer to enforce the pinned owner's key."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.shared.domain.validators.obligation_kind_validation import (
    ObligationKindValidation,
)
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class KeyEnforcementObligation:
    """Require the consumer to enforce the pinned owner's key."""

    owner: PinnedDefinitionReference
    key: KeyId
    kind: Literal["key_enforcement"] = "key_enforcement"

    def __post_init__(self) -> None:
        """Require the exact typed owner and key."""
        RuntimeTypeValidation.require_exact(
            value=self.owner, expected=PinnedDefinitionReference, field="Key owner"
        )
        RuntimeTypeValidation.require_exact(value=self.key, expected=KeyId, field="Key")

        ObligationKindValidation.require_kind(value=self.kind, expected="key_enforcement")
