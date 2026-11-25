"""Shared checks for modeled definition bodies and their attributes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.errors.attribute_already_exists_error import (
    AttributeAlreadyExistsError,
)
from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition
from domain_kernel.shared.domain.enums.collection_kind import CollectionKind
from domain_kernel.shared.domain.enums.nullability import Nullability
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


class DefinitionPartsValidation:
    """Check constraints shared by multiple definition body types."""

    @staticmethod
    def require_body_kind(*, kind: DefinitionKind, expected: DefinitionKind) -> None:
        """Require the exact kind associated with a definition body."""
        RuntimeTypeValidation.require_exact(
            value=kind, expected=DefinitionKind, field="Definition kind"
        )
        if kind is not expected:
            message = f"Definition kind must be {expected.name}"
            raise ValueError(message)

    @staticmethod
    def snapshot_attributes(
        *, attributes: Sequence[AttributeDefinition]
    ) -> tuple[AttributeDefinition, ...]:
        """Freeze exact attributes and reject repeated local names or IDs."""
        snapshot = SequenceValidation.snapshot_sequence(
            items=attributes, item_type=AttributeDefinition, field="Attributes"
        )
        if len({item.name for item in snapshot}) != len(snapshot) or len(
            {item.id for item in snapshot}
        ) != len(snapshot):
            raise AttributeAlreadyExistsError
        return snapshot

    @staticmethod
    def is_required_single(*, field: AttributeDefinition) -> bool:
        """Return whether the attribute requires exactly one nonnull value."""
        return (
            field.required
            and field.collection is CollectionKind.SINGLE
            and field.nullability is Nullability.FORBIDDEN
        )
