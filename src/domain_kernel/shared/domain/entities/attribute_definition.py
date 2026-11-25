"""One typed business field with a stable identity and lookup name."""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, Unpack
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.shared.contracts import Count
from domain_kernel.shared.domain.enums.collection_kind import CollectionKind
from domain_kernel.shared.domain.enums.data_type import DataType
from domain_kernel.shared.domain.enums.nullability import Nullability
from domain_kernel.shared.domain.policies.naming import resolve_names
from domain_kernel.shared.domain.value_objects.concept_reference_type import ConceptReferenceType
from domain_kernel.shared.domain.value_objects.constraint_definition import ConstraintDefinition
from domain_kernel.shared.domain.value_objects.scalar_value_type import ScalarValueType
from domain_kernel.shared.domain.value_objects.structured_value_type import StructuredValueType
from domain_kernel.shared.domain.value_objects.terminology import Terminology
from domain_kernel.shared.domain.value_objects.value_set_type import ValueSetType
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference
    from domain_kernel.shared.domain.types.attribute_snapshot import AttributeSnapshot
    from domain_kernel.shared.domain.types.attribute_type import AttributeType
    from domain_kernel.shared.domain.value_objects.decimal_facets import DecimalFacets


def _require_attribute_type(*, value_type: AttributeType) -> None:
    if type(value_type) not in (
        ScalarValueType,
        ConceptReferenceType,
        ValueSetType,
        StructuredValueType,
    ):
        raise TypeError("Value type must be a supported AttributeType")


def _collection_minimum(
    *,
    collection: CollectionKind,
    minimum: Count | None,
    maximum: Count | None,
    nullability: Nullability,
) -> Count | None:
    RuntimeTypeValidation.require_exact(
        value=collection, expected=CollectionKind, field="Collection kind"
    )
    RuntimeTypeValidation.require_exact(
        value=nullability, expected=Nullability, field="Nullability"
    )
    if minimum is not None:
        RuntimeTypeValidation.require_exact(
            value=minimum, expected=Count, field="Collection minimum"
        )
    if maximum is not None:
        RuntimeTypeValidation.require_exact(
            value=maximum, expected=Count, field="Collection maximum"
        )
    if collection is CollectionKind.SINGLE:
        if minimum is not None or maximum is not None:
            raise ValueError("SINGLE fields require both item bounds to be None")
        return None
    if nullability is not Nullability.FORBIDDEN:
        raise ValueError("Collections and their items forbid null values")
    resolved_minimum = Count(value=0) if minimum is None else minimum
    if maximum is not None and maximum.value < resolved_minimum.value:
        raise ValueError("The collection maximum must be at least the minimum")
    return resolved_minimum


@dataclass(frozen=True, kw_only=True, init=False)
class AttributeDefinition:
    """One typed business field with a stable identity and lookup name."""

    id: AttributeId
    name: str
    display_name: str
    value_type: AttributeType
    required: bool
    collection: CollectionKind
    min_items: Count | None
    max_items: Count | None
    nullability: Nullability
    constraints: tuple[ConstraintDefinition, ...]
    terminology: Terminology

    def __init__(  # noqa: PLR0913 -- independent public field options.
        self,
        *,
        value_type: AttributeType,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
    ) -> None:
        """Create an attribute from its exact value type and field options."""
        name, display_name = resolve_names(name=name, display_name=display_name)
        self._initialize(
            id=AttributeId(value=uuid4().hex),
            name=name,
            display_name=display_name,
            value_type=value_type,
            required=required,
            collection=collection,
            min_items=min_items,
            max_items=max_items,
            nullability=nullability,
            constraints=constraints,
            terminology=Terminology() if terminology is None else terminology,
        )

    @classmethod
    def _from_snapshot(cls, **fields: Unpack[AttributeSnapshot]) -> Self:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(  # noqa: PLR0913 - Check each independent stored field.
        self,
        *,
        id: AttributeId,  # noqa: A002 - Stored field name.
        name: str,
        display_name: str,
        value_type: AttributeType,
        required: bool,
        collection: CollectionKind,
        min_items: Count | None,
        max_items: Count | None,
        nullability: Nullability,
        constraints: Sequence[ConstraintDefinition],
        terminology: Terminology,
    ) -> None:
        RuntimeTypeValidation.require_exact(
            value=id, expected=AttributeId, field="Attribute identity"
        )
        _ = resolve_names(name=name, display_name=display_name)
        _require_attribute_type(value_type=value_type)
        RuntimeTypeValidation.require_exact(value=required, expected=bool, field="Required")
        RuntimeTypeValidation.require_exact(
            value=terminology, expected=Terminology, field="Attribute terminology"
        )
        min_items = _collection_minimum(
            collection=collection,
            minimum=min_items,
            maximum=max_items,
            nullability=nullability,
        )
        snapshot = SequenceValidation.snapshot_sequence(
            items=constraints,
            item_type=ConstraintDefinition,
            field="Attribute constraints",
        )
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "value_type", value_type)
        object.__setattr__(self, "required", required)
        object.__setattr__(self, "collection", collection)
        object.__setattr__(self, "min_items", min_items)
        object.__setattr__(self, "max_items", max_items)
        object.__setattr__(self, "nullability", nullability)
        object.__setattr__(self, "constraints", snapshot)
        object.__setattr__(self, "terminology", terminology)

    @classmethod
    def string(  # noqa: PLR0913 -- independent public field options.
        cls,
        *,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
    ) -> AttributeDefinition:
        """Author an attribute with string values."""
        return cls(
            value_type=ScalarValueType(data_type=DataType.STRING),
            display_name=display_name,
            name=name,
            required=required,
            collection=collection,
            min_items=min_items,
            max_items=max_items,
            nullability=nullability,
            constraints=constraints,
            terminology=terminology,
        )

    @classmethod
    def decimal(  # noqa: PLR0913 -- independent public field options.
        cls,
        *,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
        facets: DecimalFacets | None = None,
    ) -> AttributeDefinition:
        """Author an exact decimal attribute with optional facets."""
        return cls(
            value_type=ScalarValueType(data_type=DataType.DECIMAL, decimal=facets),
            display_name=display_name,
            name=name,
            required=required,
            collection=collection,
            min_items=min_items,
            max_items=max_items,
            nullability=nullability,
            constraints=constraints,
            terminology=terminology,
        )

    @classmethod
    def reference(  # noqa: PLR0913 -- independent public field options.
        cls,
        *,
        target: DefinitionReference,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
    ) -> AttributeDefinition:
        """Author an attribute referencing an exact business concept."""
        return cls(
            value_type=ConceptReferenceType(concept=target),
            display_name=display_name,
            name=name,
            required=required,
            collection=collection,
            min_items=min_items,
            max_items=max_items,
            nullability=nullability,
            constraints=constraints,
            terminology=terminology,
        )

    @classmethod
    def value_set(  # noqa: PLR0913 -- independent public field options.
        cls,
        *,
        value_set: DefinitionReference,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
    ) -> AttributeDefinition:
        """Author an attribute referencing an existing vocabulary."""
        return cls(
            value_type=ValueSetType(value_set=value_set),
            display_name=display_name,
            name=name,
            required=required,
            collection=collection,
            min_items=min_items,
            max_items=max_items,
            nullability=nullability,
            constraints=constraints,
            terminology=terminology,
        )


def replace_attribute_type(
    *, attribute: AttributeDefinition, value_type: AttributeType
) -> AttributeDefinition:
    """Rewrite an attribute's captured type while holding its identity and metadata fixed."""
    if value_type == attribute.value_type:
        return attribute
    _require_attribute_type(value_type=value_type)
    result = copy(attribute)
    object.__setattr__(result, "value_type", value_type)
    return result
