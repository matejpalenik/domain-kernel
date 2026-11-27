"""Named business meaning with direct fields and local keys."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.entities.key_definition import KeyDefinition
from domain_kernel.shared.domain.errors.key_already_exists_error import KeyAlreadyExistsError
from domain_kernel.shared.domain.validators.definition_parts_validation import (
    DefinitionPartsValidation,
)
from domain_kernel.shared.domain.value_objects.structured_value_type import StructuredValueType
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition


@dataclass(frozen=True, kw_only=True)
class ConceptDefinition:
    """Named business meaning with direct fields and local keys."""

    attributes: Sequence[AttributeDefinition] = ()
    keys: Sequence[KeyDefinition] = ()
    kind: Literal[DefinitionKind.CONCEPT] = DefinitionKind.CONCEPT

    def __post_init__(self) -> None:
        """Check names and enforce exact, non-null local key fields."""
        DefinitionPartsValidation.require_body_kind(kind=self.kind, expected=DefinitionKind.CONCEPT)

        attributes = DefinitionPartsValidation.snapshot_attributes(attributes=self.attributes)
        keys = SequenceValidation.snapshot_sequence(
            items=self.keys, item_type=KeyDefinition, field="Keys"
        )
        if len({item.name for item in keys}) != len(keys) or len({item.id for item in keys}) != len(
            keys
        ):
            raise KeyAlreadyExistsError

        by_id = {field.id: field for field in attributes}

        for key in keys:
            for attribute_id in key.attributes:
                field = by_id.get(attribute_id)
                if field is None:
                    raise ValueError("Key fields must belong to the owning concept")
                if not DefinitionPartsValidation.is_required_single(field=field) or isinstance(
                    field.value_type, StructuredValueType
                ):
                    raise ValueError(
                        "Key fields must be required, single-valued and non-null leaves"
                    )

        object.__setattr__(self, "attributes", attributes)
        object.__setattr__(self, "keys", keys)
