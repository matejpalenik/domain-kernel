"""Inert model rules and portable cardinality constraints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.shared.contracts import Count
from domain_kernel.shared.domain.data_shapes import (
    ConstraintDefinition,
    require_definition_reference,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class AttributeEquals:
    """A trigger whose state is represented by one scalar attribute value."""

    attribute: AttributeId
    value: str | int | bool

    def __post_init__(self) -> None:
        """Require a stable modeled attribute and a supported native value."""
        RuntimeTypeValidation.require_exact(
            value=self.attribute, expected=AttributeId, field="Rule attribute"
        )
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
            RuntimeTypeValidation.require_exact(
                value=self.when, expected=AttributeEquals, field="Rule trigger"
            )
            if self.applicable_class is not None:
                raise ValueError("Use at most one applicability condition.")
        if self.minimum is None and self.maximum is None:
            raise ValueError("Specify at least one rule bound.")
        if self.minimum is not None:
            RuntimeTypeValidation.require_exact(
                value=self.minimum, expected=Count, field="Minimum count"
            )
        if self.maximum is not None:
            RuntimeTypeValidation.require_exact(
                value=self.maximum, expected=Count, field="Maximum count"
            )
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
        TextValidation.require_text(value=self.statement, field="Rule statement")
        if self.cardinality is not None:
            RuntimeTypeValidation.require_exact(
                value=self.cardinality, expected=CardinalityRule, field="Rule cardinality"
            )
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=DefinitionKind, field="Rule kind"
        )
        if self.kind is not DefinitionKind.RULE:
            raise ValueError("Use the RULE definition kind")
        object.__setattr__(
            self,
            "constraints",
            SequenceValidation.snapshot_sequence(
                items=self.constraints,
                item_type=ConstraintDefinition,
                field="Rule constraints",
            ),
        )
