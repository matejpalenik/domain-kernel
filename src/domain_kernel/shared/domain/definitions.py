"""Immutable model definition bodies and inspected snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Generic, Literal, TypeVar, override

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_origin import DefinitionOrigin
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.attribute_already_exists_error import (
    AttributeAlreadyExistsError,
)
from domain_kernel.modeling.domain.errors.attribute_not_found_error import AttributeNotFoundError
from domain_kernel.modeling.domain.errors.definition_errors import DefinitionKindMismatchError
from domain_kernel.modeling.domain.errors.key_already_exists_error import KeyAlreadyExistsError
from domain_kernel.modeling.domain.errors.key_not_found_error import KeyNotFoundError
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.shared.contracts import ModelScope
from domain_kernel.shared.domain.acceptance import AcceptanceCheckDefinition
from domain_kernel.shared.domain.business_decisions import RuleDefinition
from domain_kernel.shared.domain.data_shapes import (
    AttributeDefinition,
    KeyDefinition,
    QuantityBinding,
    ScalarValueType,
    StructuredValueType,
    ValueSetType,
    require_definition_reference,
)
from domain_kernel.shared.domain.model_values import (
    BusinessCode,
    CollectionKind,
    DataType,
    LabelText,
    MeaningText,
    Nullability,
    RelationshipCardinality,
    Terminology,
    ValueSetMembership,
)
from domain_kernel.shared.domain.naming import require_lookup_name
from domain_kernel.shared.domain.ontology_assets import OntologyTermReference, require_unit_term
from domain_kernel.shared.domain.relation_types import RelationTypeRef
from domain_kernel.shared.domain.schema_origins import SchemaOrigin
from domain_kernel.shared.domain.semantic_definitions import (
    OntologyModuleDefinition,
    SemanticLinkDefinition,
)
from domain_kernel.shared.domain.value_objects.business_decision_definition import (
    BusinessDecisionDefinition,
)
from domain_kernel.shared.domain.value_objects.process_definition import ProcessDefinition
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference


_EMPTY_TERMINOLOGY = Terminology()


def _require_body_kind(*, kind: DefinitionKind, expected: DefinitionKind) -> None:
    RuntimeTypeValidation.require_exact(
        value=kind, expected=DefinitionKind, field="Definition kind"
    )
    if kind is not expected:
        message = f"Definition kind must be {expected.name}"
        raise ValueError(message)


def _snapshot_attributes(
    *, attributes: Sequence[AttributeDefinition]
) -> tuple[AttributeDefinition, ...]:
    snapshot = SequenceValidation.snapshot_sequence(
        items=attributes, item_type=AttributeDefinition, field="Attributes"
    )
    if len({item.name for item in snapshot}) != len(snapshot) or len(
        {item.id for item in snapshot}
    ) != len(snapshot):
        raise AttributeAlreadyExistsError
    return snapshot


def _required_single(*, field: AttributeDefinition) -> bool:
    return (
        field.required
        and field.collection is CollectionKind.SINGLE
        and field.nullability is Nullability.FORBIDDEN
    )


@unique
class EvidenceBasis(StrEnum):
    """How a definition's interpretation was established."""

    DOCUMENTED = "documented"
    DATA_INFERENCE = "data_inference"
    HYPOTHESIS = "hypothesis"
    STATEMENT = "statement"


@dataclass(frozen=True, kw_only=True)
class ConceptDefinition:
    """Named business meaning with direct fields and local keys."""

    attributes: Sequence[AttributeDefinition] = ()
    keys: Sequence[KeyDefinition] = ()
    kind: Literal[DefinitionKind.CONCEPT] = DefinitionKind.CONCEPT

    def __post_init__(self) -> None:
        """Check names and enforce exact, non-null local key fields."""
        _require_body_kind(kind=self.kind, expected=DefinitionKind.CONCEPT)
        attributes = _snapshot_attributes(attributes=self.attributes)
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
                if not _required_single(field=field) or isinstance(
                    field.value_type, StructuredValueType
                ):
                    raise ValueError(
                        "Key fields must be required, single-valued and non-null leaves"
                    )
        object.__setattr__(self, "attributes", attributes)
        object.__setattr__(self, "keys", keys)


@dataclass(frozen=True, kw_only=True)
class StructuredValueDefinition:
    """Reusable embedded fields and an optional quantity binding."""

    attributes: Sequence[AttributeDefinition]
    quantity: QuantityBinding | None = None
    kind: Literal[DefinitionKind.STRUCTURED_VALUE] = DefinitionKind.STRUCTURED_VALUE

    def __post_init__(self) -> None:
        """Validate the declared local shape of an embeddable value."""
        _require_body_kind(kind=self.kind, expected=DefinitionKind.STRUCTURED_VALUE)
        attributes = _snapshot_attributes(attributes=self.attributes)
        if not attributes:
            raise ValueError("A structured value needs at least one field")
        if self.quantity is not None:
            RuntimeTypeValidation.require_exact(
                value=self.quantity, expected=QuantityBinding, field="Quantity binding"
            )
            _validate_quantity_fields(attributes=attributes, quantity=self.quantity)
        object.__setattr__(self, "attributes", attributes)


def _validate_quantity_fields(
    *, attributes: tuple[AttributeDefinition, ...], quantity: QuantityBinding
) -> None:
    by_id = {field.id: field for field in attributes}
    magnitude = by_id.get(quantity.magnitude)
    unit = by_id.get(quantity.unit)
    if magnitude is None or unit is None:
        raise ValueError("Quantity magnitude and unit must be fields on this structured value")
    if (
        not _required_single(field=magnitude)
        or not isinstance(magnitude.value_type, ScalarValueType)
        or magnitude.value_type.data_type is not DataType.DECIMAL
    ):
        raise ValueError("Quantity magnitude must be a required, single-valued non-null decimal")
    if not _required_single(field=unit) or not isinstance(unit.value_type, ValueSetType):
        raise ValueError("Quantity unit must be a required, single-valued non-null value-set field")


@dataclass(frozen=True, kw_only=True)
class UnitDefinition:
    """Reusable unit with an optional symbol and an exact authored term."""

    symbol: str | None = None
    ontology_term: OntologyTermReference | None = None
    kind: Literal[DefinitionKind.UNIT] = DefinitionKind.UNIT

    def __post_init__(self) -> None:
        """Preserve optional display and declared external identity separately."""
        _require_body_kind(kind=self.kind, expected=DefinitionKind.UNIT)
        if self.symbol is not None:
            TextValidation.require_text(value=self.symbol, field="Unit symbol")
        if self.ontology_term is not None:
            require_unit_term(term=self.ontology_term)


@dataclass(frozen=True, kw_only=True)
class ValueSetMember:
    """One exact business code and its authored meaning."""

    code: BusinessCode
    label: LabelText
    meaning: MeaningText
    ontology_term: OntologyTermReference | None = None
    terminology: Terminology = _EMPTY_TERMINOLOGY
    unit: DefinitionReference | None = None

    def __post_init__(self) -> None:
        """Validate the vocabulary member and its exclusive unit bindings."""
        RuntimeTypeValidation.require_exact(
            value=self.code, expected=BusinessCode, field="Member code"
        )
        RuntimeTypeValidation.require_exact(
            value=self.label, expected=LabelText, field="Member label"
        )
        RuntimeTypeValidation.require_exact(
            value=self.meaning, expected=MeaningText, field="Member meaning"
        )
        RuntimeTypeValidation.require_exact(
            value=self.terminology, expected=Terminology, field="Member terminology"
        )
        if self.ontology_term is not None:
            RuntimeTypeValidation.require_exact(
                value=self.ontology_term, expected=OntologyTermReference, field="Member term"
            )
        if self.unit is not None:
            require_definition_reference(value=self.unit, field="Member unit")
            if self.ontology_term is not None:
                raise ValueError("Supply a unit or ontology term for a code, never both")


@dataclass(frozen=True, kw_only=True)
class ValueSetDefinition:
    """A closed or open vocabulary of distinct known codes."""

    membership: ValueSetMembership
    members: Sequence[ValueSetMember]
    kind: Literal[DefinitionKind.VALUE_SET] = DefinitionKind.VALUE_SET

    def __post_init__(self) -> None:
        """Keep ordered member metadata with distinct exact codes."""
        _require_body_kind(kind=self.kind, expected=DefinitionKind.VALUE_SET)
        RuntimeTypeValidation.require_exact(
            value=self.membership, expected=ValueSetMembership, field="Membership"
        )
        members = SequenceValidation.snapshot_sequence(
            items=self.members, item_type=ValueSetMember, field="Members"
        )
        if not members:
            raise ValueError("A value set requires at least one known code")
        if len({item.code for item in members}) != len(members):
            raise ValueError("Value-set codes must be distinct")
        object.__setattr__(self, "members", members)


@dataclass(frozen=True, kw_only=True)
class RelationshipDefinition:
    """A binary relationship with distinct directional bounds."""

    source_concept_id: DefinitionReference
    target_concept_id: DefinitionReference
    cardinality: RelationshipCardinality
    kind: Literal[DefinitionKind.RELATIONSHIP] = DefinitionKind.RELATIONSHIP
    relation_type: RelationTypeRef | None = None

    def __post_init__(self) -> None:
        """Keep direction and exact concept references explicit."""
        _require_body_kind(kind=self.kind, expected=DefinitionKind.RELATIONSHIP)
        require_definition_reference(value=self.source_concept_id, field="Relationship source")
        require_definition_reference(value=self.target_concept_id, field="Relationship target")
        RuntimeTypeValidation.require_exact(
            value=self.cardinality, expected=RelationshipCardinality, field="Cardinality"
        )
        if self.relation_type is not None:
            RuntimeTypeValidation.require_exact(
                value=self.relation_type, expected=RelationTypeRef, field="Directed relation type"
            )


type DefinitionBody = (
    ConceptDefinition
    | StructuredValueDefinition
    | UnitDefinition
    | ValueSetDefinition
    | RelationshipDefinition
    | AcceptanceCheckDefinition
    | ProcessDefinition
    | BusinessDecisionDefinition
    | RuleDefinition
    | SemanticLinkDefinition
    | OntologyModuleDefinition
)


def require_definition_body(*, body: DefinitionBody) -> None:
    """Require one exact currently implemented body record."""
    if type(body) not in (
        ConceptDefinition,
        StructuredValueDefinition,
        UnitDefinition,
        ValueSetDefinition,
        RelationshipDefinition,
        AcceptanceCheckDefinition,
        ProcessDefinition,
        BusinessDecisionDefinition,
        RuleDefinition,
        SemanticLinkDefinition,
        OntologyModuleDefinition,
    ):
        raise TypeError("Use an implemented definition body")


BodyT_co = TypeVar("BodyT_co", bound=DefinitionBody, covariant=True, default=DefinitionBody)


@dataclass(frozen=True, kw_only=True)
class Definition(Generic[BodyT_co]):
    """Detached definition revision in an exact owning model scope."""

    id: DefinitionId
    scope: ModelScope
    revision: int
    name: str
    display_name: str
    meaning: str
    body: BodyT_co
    aliases: Sequence[str] = ()
    terminology: Terminology = _EMPTY_TERMINOLOGY
    origin: DefinitionOrigin = DefinitionOrigin.COMPANY
    status: DefinitionStatus = DefinitionStatus.PROPOSED
    basis: EvidenceBasis = EvidenceBasis.HYPOTHESIS
    decision_ids: Sequence[DecisionId] = ()
    rationale: str | None = None
    baseline_definition_id: DefinitionId | None = None
    replacement_ids: Sequence[DefinitionId] = ()
    schema_origins: Sequence[SchemaOrigin] = field(default=(), metadata={"wire_omit_empty": True})

    evidence: Sequence[Evidence] = field(default=(), metadata={"wire_omit_empty": True})

    def __post_init__(self) -> None:
        """Snapshot one appropriately identified and typed definition revision."""
        RuntimeTypeValidation.require_exact(
            value=self.id, expected=DefinitionId, field="Definition ID"
        )
        RuntimeTypeValidation.require_exact(
            value=self.scope, expected=ModelScope, field="Definition scope"
        )
        RuntimeTypeValidation.require_exact(
            value=self.revision, expected=int, field="Definition revision"
        )
        if self.revision < 1:
            raise ValueError("Definition revision must be positive")
        require_lookup_name(name=self.name)
        TextValidation.require_text(value=self.display_name, field="Display name")
        TextValidation.require_text(value=self.meaning, field="Definition meaning")
        require_definition_body(body=self.body)
        RuntimeTypeValidation.require_exact(
            value=self.terminology, expected=Terminology, field="Definition terminology"
        )
        RuntimeTypeValidation.require_exact(
            value=self.origin, expected=DefinitionOrigin, field="Definition origin"
        )
        RuntimeTypeValidation.require_exact(
            value=self.status, expected=DefinitionStatus, field="Definition status"
        )
        RuntimeTypeValidation.require_exact(
            value=self.basis, expected=EvidenceBasis, field="Definition basis"
        )
        if self.baseline_definition_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.baseline_definition_id,
                expected=DefinitionId,
                field="Baseline definition ID",
            )
        if self.rationale is not None:
            TextValidation.require_text(value=self.rationale, field="Definition rationale")
        aliases = SequenceValidation.snapshot_sequence(
            items=self.aliases, item_type=str, field="Aliases"
        )
        decision_ids = SequenceValidation.snapshot_sequence(
            items=self.decision_ids, item_type=DecisionId, field="Decisions"
        )
        replacements = SequenceValidation.snapshot_sequence(
            items=self.replacement_ids, item_type=DefinitionId, field="Replacement IDs"
        )
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "decision_ids", decision_ids)
        object.__setattr__(self, "replacement_ids", replacements)
        object.__setattr__(
            self,
            "schema_origins",
            SequenceValidation.snapshot_sequence(
                items=self.schema_origins, item_type=SchemaOrigin, field="Schema origins"
            ),
        )

        citations = SequenceValidation.snapshot_sequence(
            items=self.evidence, item_type=Evidence, field="Evidence"
        )
        if len({item.id for item in citations}) != len(citations):
            raise ValueError("Cite each exact source occurrence once")
        object.__setattr__(self, "evidence", citations)

    @property
    def kind(self) -> DefinitionKind:
        """Return the exact kind of this revision's body."""
        return self.body.kind


def require_definition_selector(
    *, name: str | None, item_id: object, id_type: type[object]
) -> None:
    """Require one exact name or the specified nominal identifier."""
    if (name is None) == (item_id is None):
        raise ValueError("Supply exactly one name or ID")
    if name is not None:
        TextValidation.require_text(value=name, field="Lookup name")
    else:
        RuntimeTypeValidation.require_exact(value=item_id, expected=id_type, field="Lookup ID")


@dataclass(frozen=True, kw_only=True)
class Concept(Definition[ConceptDefinition]):
    """An inspected concept with direct, snapshot-local reads."""

    @override
    def __post_init__(self) -> None:
        """Check the specialization while preserving the definition record layout."""
        super().__post_init__()
        RuntimeTypeValidation.require_exact(
            value=self.body, expected=ConceptDefinition, field="Concept body"
        )

    @property
    def attributes(self) -> tuple[AttributeDefinition, ...]:
        """Return this revision's direct attributes."""
        return tuple(self.body.attributes)

    @property
    def keys(self) -> tuple[KeyDefinition, ...]:
        """Return this revision's local keys."""
        return tuple(self.body.keys)

    def get_attribute(
        self, *, name: str | None = None, attribute_id: AttributeId | None = None
    ) -> AttributeDefinition:
        """Find one inspected attribute by one exact selector."""
        require_definition_selector(name=name, item_id=attribute_id, id_type=AttributeId)
        for attribute in self.body.attributes:
            if attribute.id == attribute_id or attribute.name == name:
                return attribute
        raise AttributeNotFoundError

    def get_key(self, *, name: str | None = None, key_id: KeyId | None = None) -> KeyDefinition:
        """Find one inspected key by one exact selector."""
        require_definition_selector(name=name, item_id=key_id, id_type=KeyId)
        for key in self.body.keys:
            if key.id == key_id or key.name == name:
                return key
        raise KeyNotFoundError


def typed_definition[T: DefinitionBody](
    *,
    value: Definition,
    body_type: type[T],
    view_type: type[Definition[T]],
) -> Definition[T]:
    """Materialize the exact inspected definition through a typed snapshot view."""
    if not isinstance(value.body, body_type):
        raise DefinitionKindMismatchError
    return view_type(
        id=value.id,
        scope=value.scope,
        revision=value.revision,
        name=value.name,
        display_name=value.display_name,
        meaning=value.meaning,
        body=value.body,
        aliases=value.aliases,
        terminology=value.terminology,
        origin=value.origin,
        status=value.status,
        basis=value.basis,
        decision_ids=value.decision_ids,
        rationale=value.rationale,
        baseline_definition_id=value.baseline_definition_id,
        replacement_ids=value.replacement_ids,
        schema_origins=value.schema_origins,
        evidence=value.evidence,
    )
