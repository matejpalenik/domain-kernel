"""Describe the results a decision-table rule assigns under stated conditions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId
from domain_kernel.shared.domain.value_objects.decision_value import DecisionValue
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

_OUTPUT_PAIR_LENGTH = 2


@dataclass(frozen=True, kw_only=True)
class DecisionRule:
    """A descriptive rule assigning exact values to named outputs."""

    id: str
    condition_ids: Sequence[ConditionId]
    output_values: Sequence[tuple[str, DecisionValue]]
    evidence: tuple[()] = ()

    def __post_init__(self) -> None:
        """Detach a fixed-position output pair per declared result."""
        TextValidation.require_text(value=self.id, field="Decision rule key")
        conditions = SequenceValidation.snapshot_sequence(
            items=self.condition_ids,
            item_type=ConditionId,
            field="Rule condition IDs",
        )
        if len(set(conditions)) != len(conditions):
            raise ValueError("Use distinct rule conditions")
        if not SequenceValidation.is_non_string_sequence(value=self.output_values):
            raise TypeError("Use a sequence of fixed output pairs")
        values = tuple(self.output_values)
        for item in values:
            if type(item) is not tuple or len(item) != _OUTPUT_PAIR_LENGTH:
                raise TypeError("Use (output key, decision value) tuples")
            TextValidation.require_text(value=item[0], field="Rule output key")
            RuntimeTypeValidation.require_exact(
                value=item[1], expected=DecisionValue, field="Rule output value"
            )
        if len({key for key, _ in values}) != len(values):
            raise ValueError("Set each rule output once")
        if not SequenceValidation.is_non_string_sequence(value=self.evidence) or self.evidence:
            raise ValueError("Capture source revisions before attaching decision evidence")
        object.__setattr__(self, "condition_ids", conditions)
        object.__setattr__(self, "output_values", values)
        object.__setattr__(self, "evidence", ())
