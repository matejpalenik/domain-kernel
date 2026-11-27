"""Validate the structure of a descriptive decision table without running it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.entities.condition import Condition
from domain_kernel.shared.domain.enums.hit_policy import HitPolicy
from domain_kernel.shared.domain.errors.process_part_already_exists_error import (
    ProcessPartAlreadyExistsError,
)
from domain_kernel.shared.domain.value_objects.decision_input import DecisionInput
from domain_kernel.shared.domain.value_objects.decision_output import DecisionOutput
from domain_kernel.shared.domain.value_objects.decision_rule import DecisionRule
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId


@dataclass(frozen=True, kw_only=True)
class BusinessDecisionDefinition:
    """An immutable decision table with owner-local conditions and ordered rules."""

    inputs: Sequence[DecisionInput]
    outputs: Sequence[DecisionOutput]
    conditions: Sequence[Condition]
    rules: Sequence[DecisionRule]
    hit_policy: HitPolicy = HitPolicy.UNIQUE
    kind: Literal[DefinitionKind.BUSINESS_DECISION] = DefinitionKind.BUSINESS_DECISION

    def __post_init__(self) -> None:
        """Freeze parts, then validate symbols and rule bindings."""
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=DefinitionKind, field="Decision kind"
        )
        RuntimeTypeValidation.require_exact(
            value=self.hit_policy, expected=HitPolicy, field="Decision hit policy"
        )
        if self.kind is not DefinitionKind.BUSINESS_DECISION:
            raise ValueError("Use the BUSINESS_DECISION definition kind")

        self._freeze_parts()
        self._verify_symbols()
        self._verify_rules()

    def _freeze_parts(self) -> None:
        """Detach the inputs, outputs, conditions and rules in their authored order."""
        for field, collection, part in (
            ("inputs", self.inputs, DecisionInput),
            ("outputs", self.outputs, DecisionOutput),
            ("conditions", self.conditions, Condition),
            ("rules", self.rules, DecisionRule),
        ):
            object.__setattr__(
                self,
                field,
                SequenceValidation.snapshot_sequence(items=collection, item_type=part, field=field),
            )

    def _verify_symbols(self) -> None:
        """Require unique local keys and bind conditions to declared inputs."""
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
        """Check rule conditions, output types and uniqueness under the hit policy."""
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
