"""Types and fields used by business definitions."""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Literal, Self, TypedDict, Unpack
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.contracts import Count, PinnedDefinitionReference
from domain_kernel.shared.domain.model_values import (
    CollectionKind,
    DataType,
    DecimalFacets,
    Nullability,
    Terminology,
)
from domain_kernel.shared.domain.naming import resolve_names
from domain_kernel.shared.domain.ontology_assets import OntologyTermReference, require_unit_term
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference
    from domain_kernel.shared.domain.model_values import ScalarDataType


def require_definition_reference(*, value: DefinitionReference, field: str) -> None:
    """Require an explicitly typed local, pack-local or exactly pinned reference."""
    if type(value) not in (DefinitionId, PinnedDefinitionReference, ReferenceDefinitionId):
        message = f"{field} must be a typed definition reference"
        raise TypeError(message)


def _require_kind(*, kind: str, expected: str) -> None:
    RuntimeTypeValidation.require_exact(value=kind, expected=str, field="Attribute type kind")
    if kind != expected:
        message = f"Attribute type kind must be '{expected}'"
        raise ValueError(message)


_SCALAR_TYPES = frozenset(
    {
        DataType.STRING,
        DataType.INTEGER,
        DataType.DECIMAL,
        DataType.BOOLEAN,
        DataType.DATE,
        DataType.DATETIME,
    }
)


@dataclass(frozen=True, kw_only=True)
class ScalarValueType:
    """Type of an exact scalar business value."""

    data_type: ScalarDataType
    decimal: DecimalFacets | None = None
    kind: Literal["scalar"] = "scalar"

    def __post_init__(self) -> None:
        """Limit facets to exact decimal types and require the fixed tag."""
        _require_kind(kind=self.kind, expected="scalar")
        RuntimeTypeValidation.require_exact(
            value=self.data_type, expected=DataType, field="Scalar data type"
        )
        if self.data_type not in _SCALAR_TYPES:
            raise ValueError("Choose a scalar data type for ScalarValueType")
        if self.decimal is not None:
            RuntimeTypeValidation.require_exact(
                value=self.decimal, expected=DecimalFacets, field="Scalar facets"
            )
            if self.data_type is not DataType.DECIMAL:
                raise ValueError("Decimal facets require the DECIMAL data type")


@dataclass(frozen=True, kw_only=True)
class ConceptReferenceType:
    """Reference to a business concept."""

    concept: DefinitionReference
    kind: Literal["concept_reference"] = "concept_reference"

    def __post_init__(self) -> None:
        """Preserve the exact typed concept reference."""
        _require_kind(kind=self.kind, expected="concept_reference")
        require_definition_reference(value=self.concept, field="Concept")


@dataclass(frozen=True, kw_only=True)
class ValueSetType:
    """Reference to a vocabulary of business codes."""

    value_set: DefinitionReference
    kind: Literal["value_set"] = "value_set"

    def __post_init__(self) -> None:
        """Preserve the exact typed vocabulary reference."""
        _require_kind(kind=self.kind, expected="value_set")
        require_definition_reference(value=self.value_set, field="Value set")


@dataclass(frozen=True, kw_only=True)
class StructuredValueType:
    """Embed a reusable structured value."""

    structure: DefinitionReference
    kind: Literal["structured_value"] = "structured_value"

    def __post_init__(self) -> None:
        """Preserve the exact typed embedding reference."""
        _require_kind(kind=self.kind, expected="structured_value")
        require_definition_reference(value=self.structure, field="Structure")


type AttributeType = ScalarValueType | ConceptReferenceType | ValueSetType | StructuredValueType


@unique
class ConstraintLanguage(StrEnum):
    """Representation of a recorded constraint."""

    TEXT = "text"
    JSON_SCHEMA = "json_schema"
    SHACL = "shacl"


@unique
class ConstraintTarget(StrEnum):
    """Whether a constraint describes the model or its instances."""

    MODEL = "model"
    INSTANCE = "instance"


@dataclass(frozen=True, kw_only=True)
class ConstraintDefinition:
    """Inert, attributed constraint text for later interpretation."""

    id: str
    description: str
    language: ConstraintLanguage
    expression: str
    target: ConstraintTarget = ConstraintTarget.MODEL

    def __post_init__(self) -> None:
        """Keep authored constraint text inert and validate its declared target."""
        TextValidation.require_text(value=self.id, field="Constraint ID")
        TextValidation.require_text(value=self.description, field="Constraint description")
        TextValidation.require_text(value=self.expression, field="Constraint expression")
        RuntimeTypeValidation.require_exact(
            value=self.language, expected=ConstraintLanguage, field="Constraint language"
        )
        RuntimeTypeValidation.require_exact(
            value=self.target, expected=ConstraintTarget, field="Constraint target"
        )


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


class _AttributeSnapshot(TypedDict):
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
    def _from_snapshot(cls, **fields: Unpack[_AttributeSnapshot]) -> Self:
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


@dataclass(frozen=True, kw_only=True, init=False)
class KeyDefinition:
    """Named identity requirement over direct attributes of an owning concept."""

    id: KeyId
    name: str
    display_name: str
    attributes: tuple[AttributeId, ...]

    def __init__(
        self,
        *,
        attributes: Sequence[AttributeId],
        display_name: str | None = None,
        name: str | None = None,
    ) -> None:
        """Give a business key its own opaque identity."""
        name, display_name = resolve_names(name=name, display_name=display_name)
        self._initialize(
            id=KeyId(value=uuid4().hex), name=name, display_name=display_name, attributes=attributes
        )

    @classmethod
    def _from_snapshot(
        cls,
        *,
        id: KeyId,  # noqa: A002 - Stored field name.
        name: str,
        display_name: str,
        attributes: Sequence[AttributeId],
    ) -> Self:
        instance = object.__new__(cls)
        instance._initialize(id=id, name=name, display_name=display_name, attributes=attributes)
        return instance

    def _initialize(
        self,
        *,
        id: KeyId,  # noqa: A002 - Stored field name.
        name: str,
        display_name: str,
        attributes: Sequence[AttributeId],
    ) -> None:
        RuntimeTypeValidation.require_exact(value=id, expected=KeyId, field="Key identity")
        _ = resolve_names(name=name, display_name=display_name)
        snapshot = SequenceValidation.snapshot_sequence(
            items=attributes, item_type=AttributeId, field="Key attributes"
        )
        if not snapshot:
            raise ValueError("A key requires at least one attribute")
        if len(set(snapshot)) != len(snapshot):
            raise ValueError("Key attributes must be distinct")
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "attributes", snapshot)


@dataclass(frozen=True, kw_only=True)
class QuantityBinding:
    """Bind magnitude and unit attributes for one structured value."""

    magnitude: AttributeId
    unit: AttributeId
    quantity_kind: OntologyTermReference | None = None

    def __post_init__(self) -> None:
        """Require distinct field IDs and validate any supplied term kind."""
        RuntimeTypeValidation.require_exact(
            value=self.magnitude, expected=AttributeId, field="Quantity magnitude"
        )
        RuntimeTypeValidation.require_exact(
            value=self.unit, expected=AttributeId, field="Quantity unit"
        )
        if self.magnitude == self.unit:
            raise ValueError("Quantity magnitude and unit must use distinct attributes")
        if self.quantity_kind is not None:
            require_unit_term(term=self.quantity_kind)


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
