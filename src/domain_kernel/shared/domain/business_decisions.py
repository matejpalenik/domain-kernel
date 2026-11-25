"""Typed descriptive decisions and their native literal values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId
from domain_kernel.shared.contracts import Count
from domain_kernel.shared.domain.data_shapes import (
    ConstraintDefinition,
    require_definition_reference,
)
from domain_kernel.shared.domain.model_values import DataType, ScalarDataType
from domain_kernel.shared.domain.records.condition import Condition
from domain_kernel.shared.errors import ProcessPartAlreadyExistsError
from domain_kernel.shared.validation import (
    is_non_string_sequence,
    require_exact,
    require_text,
    snapshot_sequence,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference


@unique
class HitPolicy(StrEnum):
    """Describe intended decision-table result selection."""

    UNIQUE = "unique"
    FIRST = "first"
    COLLECT = "collect"


type DecisionScalar = str | bool | int | Decimal | date | datetime
_OUTPUT_PAIR_LENGTH = 2
_SCALAR_TYPES: dict[type[object], ScalarDataType] = {
    str: DataType.STRING,
    bool: DataType.BOOLEAN,
    int: DataType.INTEGER,
    Decimal: DataType.DECIMAL,
    date: DataType.DATE,
    datetime: DataType.DATETIME,
}


@dataclass(frozen=True, kw_only=True)
class DecisionValue:
    """One exact native scalar literal."""

    value: DecisionScalar

    def __post_init__(self) -> None:
        """Validate native type and represent an instant in its canonical time zone."""
        if type(self.value) not in _SCALAR_TYPES:
            raise TypeError("Use an exact string, bool, integer, Decimal, date or datetime")
        if type(self.value) is Decimal and not self.value.is_finite():
            raise ValueError("Decision decimals must be finite")
        if type(self.value) is datetime:
            if self.value.utcoffset() is None:
                raise ValueError("Decision times require a time zone")
            object.__setattr__(self, "value", self.value.astimezone(UTC))

    @property
    def data_type(self) -> ScalarDataType:
        """Derive the exact scalar tag without treating bool as int or datetime as date."""
        return _SCALAR_TYPES[type(self.value)]


@dataclass(frozen=True, kw_only=True)
class DecisionInput:
    """A symbolic input backed by a model definition."""

    id: str
    name: str
    definition_id: DefinitionReference
    data_type: DataType

    def __post_init__(self) -> None:
        """Retain the exact input symbol, label, model edge and type."""
        require_text(value=self.id, field="Decision input key")
        require_text(value=self.name, field="Decision input name")
        require_definition_reference(value=self.definition_id, field="Decision input definition")
        require_exact(value=self.data_type, expected=DataType, field="Decision input type")


@dataclass(frozen=True, kw_only=True)
class DecisionOutput:
    """A named result and the scalar type expected in each table rule."""

    id: str
    name: str
    definition_id: DefinitionReference
    data_type: ScalarDataType

    def __post_init__(self) -> None:
        """Require an exact scalar output and its authored meaning."""
        require_text(value=self.id, field="Decision output key")
        require_text(value=self.name, field="Decision output name")
        require_definition_reference(value=self.definition_id, field="Decision output definition")
        require_exact(value=self.data_type, expected=DataType, field="Decision output type")
        if self.data_type not in _SCALAR_TYPES.values():
            raise ValueError("Decision outputs use scalar literals")


@dataclass(frozen=True, kw_only=True)
class DecisionRule:
    """A descriptive rule assigning exact values to named outputs."""

    id: str
    condition_ids: Sequence[ConditionId]
    output_values: Sequence[tuple[str, DecisionValue]]
    evidence: tuple[()] = ()

    def __post_init__(self) -> None:
        """Detach a fixed-position output pair per declared result."""
        require_text(value=self.id, field="Decision rule key")
        conditions = snapshot_sequence(
            items=self.condition_ids,
            item_type=ConditionId,
            field="Rule condition IDs",
        )
        if len(set(conditions)) != len(conditions):
            raise ValueError("Use distinct rule conditions")
        if not is_non_string_sequence(self.output_values):
            raise TypeError("Use a sequence of fixed output pairs")
        values = tuple(self.output_values)
        for item in values:
            if type(item) is not tuple or len(item) != _OUTPUT_PAIR_LENGTH:
                raise TypeError("Use (output key, decision value) tuples")
            require_text(value=item[0], field="Rule output key")
            require_exact(value=item[1], expected=DecisionValue, field="Rule output value")
        if len({key for key, _ in values}) != len(values):
            raise ValueError("Set each rule output once")
        if not is_non_string_sequence(self.evidence) or self.evidence:
            raise ValueError("Capture source revisions before attaching decision evidence")
        object.__setattr__(self, "condition_ids", conditions)
        object.__setattr__(self, "output_values", values)
        object.__setattr__(self, "evidence", ())


@dataclass(frozen=True, kw_only=True)
class BusinessDecisionDefinition:
    """A complete decision table for inspection and review."""

    inputs: Sequence[DecisionInput]
    outputs: Sequence[DecisionOutput]
    conditions: Sequence[Condition]
    rules: Sequence[DecisionRule]
    hit_policy: HitPolicy = HitPolicy.UNIQUE
    kind: Literal[DefinitionKind.BUSINESS_DECISION] = DefinitionKind.BUSINESS_DECISION

    def __post_init__(self) -> None:
        """Verify exact symbolic bindings and compatible rule result types."""
        require_exact(value=self.kind, expected=DefinitionKind, field="Decision kind")
        require_exact(value=self.hit_policy, expected=HitPolicy, field="Decision hit policy")
        if self.kind is not DefinitionKind.BUSINESS_DECISION:
            raise ValueError("Use the BUSINESS_DECISION definition kind")
        for field, collection, part in (
            ("inputs", self.inputs, DecisionInput),
            ("outputs", self.outputs, DecisionOutput),
            ("conditions", self.conditions, Condition),
            ("rules", self.rules, DecisionRule),
        ):
            object.__setattr__(
                self, field, snapshot_sequence(items=collection, item_type=part, field=field)
            )
        self._verify_symbols()
        self._verify_rules()

    def _verify_symbols(self) -> None:
        for parts in (self.inputs, self.outputs, self.rules):
            if len({part.id for part in parts}) != len(parts):
                raise ValueError("Use distinct input, output and rule keys")
        if len({item.id for item in self.conditions}) != len(self.conditions) or len(
            {item.name for item in self.conditions}
        ) != len(self.conditions):
            raise ProcessPartAlreadyExistsError
        inputs = {item.id for item in self.inputs}
        if any(not set(condition.input_ids) <= inputs for condition in self.conditions):
            raise ValueError("Match condition symbols to declared decision input keys")

    def _verify_rules(self) -> None:
        if not self.outputs or not self.rules:
            raise ValueError("A decision table requires outputs and rules")
        outputs = {item.id: item.data_type for item in self.outputs}
        conditions = {item.id for item in self.conditions}
        previous: set[frozenset[ConditionId]] = set()
        for rule in self.rules:
            binding = frozenset(rule.condition_ids)
            if not binding <= conditions:
                raise ValueError("Supply the exact referenced condition in this decision")
            if self.hit_policy is HitPolicy.UNIQUE and binding in previous:
                raise ValueError("Unique hit policy forbids identical rule conditions")
            previous.add(binding)
            if {key: value.data_type for key, value in rule.output_values} != outputs:
                raise ValueError(
                    "Match every rule output to its declared output key and scalar type"
                )


@dataclass(frozen=True, kw_only=True)
class AttributeEquals:
    """A trigger whose state is represented by one scalar attribute value."""

    attribute: AttributeId
    value: str | int | bool

    def __post_init__(self) -> None:
        """Require a stable modeled attribute and a supported native value."""
        require_exact(value=self.attribute, expected=AttributeId, field="Rule attribute")
        if type(self.value) not in (str, int, bool):
            raise TypeError("Use a string, integer or Boolean trigger value.")


@dataclass(frozen=True, kw_only=True)
class CardinalityRule:
    """Portable Core count restriction on one directed relationship."""

    focus: DefinitionReference
    relationship: DefinitionReference
    minimum: Count | None = None
    maximum: Count | None = None
    applicable_class: DefinitionReference | None = None
    when: AttributeEquals | None = None

    def __post_init__(self) -> None:
        """Require valid bounds and at most one applicability condition."""
        require_definition_reference(value=self.focus, field="Rule focus")
        require_definition_reference(value=self.relationship, field="Rule relationship")
        if self.applicable_class is not None:
            require_definition_reference(value=self.applicable_class, field="Applicable class")
        if self.when is not None:
            require_exact(value=self.when, expected=AttributeEquals, field="Rule trigger")
            if self.applicable_class is not None:
                raise ValueError("Use at most one applicability condition.")
        if self.minimum is None and self.maximum is None:
            raise ValueError("Specify at least one rule bound.")
        if self.minimum is not None:
            require_exact(value=self.minimum, expected=Count, field="Minimum count")
        if self.maximum is not None:
            require_exact(value=self.maximum, expected=Count, field="Maximum count")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum.value > self.maximum.value
        ):
            raise ValueError("The maximum count must be at least the minimum.")


@dataclass(frozen=True, kw_only=True)
class RuleDefinition:
    """An inert rule and any model- or instance-targeted constraints it carries."""

    statement: str
    constraints: Sequence[ConstraintDefinition] = ()
    kind: Literal[DefinitionKind.RULE] = DefinitionKind.RULE
    cardinality: CardinalityRule | None = None

    def __post_init__(self) -> None:
        """Preserve constraint targets and text without evaluating them."""
        require_text(value=self.statement, field="Rule statement")
        if self.cardinality is not None:
            require_exact(
                value=self.cardinality, expected=CardinalityRule, field="Rule cardinality"
            )
        require_exact(value=self.kind, expected=DefinitionKind, field="Rule kind")
        if self.kind is not DefinitionKind.RULE:
            raise ValueError("Use the RULE definition kind")
        object.__setattr__(
            self,
            "constraints",
            snapshot_sequence(
                items=self.constraints,
                item_type=ConstraintDefinition,
                field="Rule constraints",
            ),
        )
