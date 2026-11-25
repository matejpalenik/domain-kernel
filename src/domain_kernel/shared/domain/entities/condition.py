"""Describe inert conditions shared by processes and business decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Never, override
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId
from domain_kernel.shared.domain.entities.part_snapshot import PartSnapshot
from domain_kernel.shared.domain.policies.naming import resolve_names
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True, init=False)
class Condition(PartSnapshot):
    """An inert condition referencing owner-local input symbols."""

    id: ConditionId
    name: str
    display_name: str
    description: str
    input_ids: tuple[str, ...]
    expression: str
    evidence: tuple[()]

    def __init__(  # noqa: PLR0913 - Keep the condition's authored fields explicit.
        self,
        *,
        description: str,
        expression: str,
        display_name: str | None = None,
        name: str | None = None,
        input_ids: Sequence[str] = (),
        evidence: Sequence[Never] = (),
    ) -> None:
        """Capture declared inputs and inert condition text under a stable local ID."""
        lookup, label = resolve_names(name=name, display_name=display_name)
        self._set_fields(
            attributes={
                "id": ConditionId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "description": description,
                "input_ids": input_ids,
                "expression": expression,
                "evidence": self._snapshot_evidence(evidence=evidence),
            },
        )
        self._validate()

    @override
    def _validate(self) -> None:
        RuntimeTypeValidation.require_exact(
            value=self.id, expected=ConditionId, field="Condition ID"
        )
        self._require_names(name=self.name, display_name=self.display_name)
        TextValidation.require_text(value=self.description, field="Condition description")
        TextValidation.require_text(value=self.expression, field="Condition expression")
        inputs = SequenceValidation.snapshot_sequence(
            items=self.input_ids, item_type=str, field="Condition inputs"
        )
        for item in inputs:
            TextValidation.require_text(value=item, field="Condition input symbol")
        if len(set(inputs)) != len(inputs):
            raise ValueError("Use distinct condition input symbols")
        _ = self._snapshot_evidence(evidence=self.evidence)
        object.__setattr__(self, "input_ids", inputs)
