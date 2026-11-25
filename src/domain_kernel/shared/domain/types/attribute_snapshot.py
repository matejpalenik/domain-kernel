"""Describe the exact fields used to restore an attribute."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
    from domain_kernel.shared.contracts import Count
    from domain_kernel.shared.domain.enums.collection_kind import CollectionKind
    from domain_kernel.shared.domain.enums.nullability import Nullability
    from domain_kernel.shared.domain.types.attribute_type import AttributeType
    from domain_kernel.shared.domain.value_objects.constraint_definition import ConstraintDefinition
    from domain_kernel.shared.domain.value_objects.terminology import Terminology


class AttributeSnapshot(TypedDict):
    """Saved attribute fields, including its local identity."""

    id: AttributeId
    value_type: AttributeType
    name: str
    display_name: str
    required: bool
    collection: CollectionKind
    min_items: Count | None
    max_items: Count | None
    nullability: Nullability
    constraints: Sequence[ConstraintDefinition]
    terminology: Terminology
