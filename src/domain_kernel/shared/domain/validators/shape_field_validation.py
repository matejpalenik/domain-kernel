"""Validate typed references and discriminators in model shapes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference


class ShapeFieldValidation:
    """Check field types without resolving model references."""

    @staticmethod
    def require_definition_reference(*, value: DefinitionReference, field: str) -> None:
        """Require an explicitly typed local, pack-local or exactly pinned reference."""
        if type(value) not in (DefinitionId, PinnedDefinitionReference, ReferenceDefinitionId):
            message = f"{field} must be a typed definition reference"
            raise TypeError(message)

    @staticmethod
    def require_attribute_type_kind(*, kind: str, expected: str) -> None:
        """Require the declared attribute type discriminator."""
        RuntimeTypeValidation.require_exact(value=kind, expected=str, field="Attribute type kind")
        if kind != expected:
            message = f"Attribute type kind must be '{expected}'"
            raise ValueError(message)
