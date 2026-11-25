"""An inert rule and any model- or instance-targeted constraints it carries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.value_objects.cardinality_rule import CardinalityRule
from domain_kernel.shared.domain.value_objects.constraint_definition import ConstraintDefinition
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


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
