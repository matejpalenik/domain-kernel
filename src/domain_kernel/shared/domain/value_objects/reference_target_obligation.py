"""Require the consumer to enforce a pinned reference target."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.shared.contracts import PinnedDefinitionReference
from domain_kernel.shared.domain.validators.obligation_kind_validation import (
    ObligationKindValidation,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class ReferenceTargetObligation:
    """Require the consumer to enforce a pinned reference target."""

    owner: PinnedDefinitionReference
    attribute: AttributeId
    kind: Literal["reference_target"] = "reference_target"

    def __post_init__(self) -> None:
        """Require the exact typed owner and attribute."""
        RuntimeTypeValidation.require_exact(
            value=self.owner, expected=PinnedDefinitionReference, field="Attribute owner"
        )
        RuntimeTypeValidation.require_exact(
            value=self.attribute, expected=AttributeId, field="Attribute"
        )
        ObligationKindValidation.require_kind(value=self.kind, expected="reference_target")
