"""A reviewed condition evaluated on an exact model candidate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.enums.check_requirement import CheckRequirement
from domain_kernel.shared.domain.value_objects.distinct_definitions_check import (
    DistinctDefinitionsCheck,
)
from domain_kernel.shared.domain.value_objects.manual_criterion import ManualCriterion
from domain_kernel.shared.domain.value_objects.meaning_text import MeaningText
from domain_kernel.shared.domain.value_objects.quantity_required_check import QuantityRequiredCheck
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.acceptance_predicate import AcceptancePredicate


@dataclass(frozen=True, kw_only=True)
class AcceptanceCheckDefinition:
    """A reviewed condition evaluated on an exact model candidate."""

    statement: MeaningText
    requirement: CheckRequirement
    predicate: AcceptancePredicate
    kind: Literal[DefinitionKind.ACCEPTANCE_CHECK] = DefinitionKind.ACCEPTANCE_CHECK

    def __post_init__(self) -> None:
        """Capture a closed, typed predicate and requirement."""
        RuntimeTypeValidation.require_exact(
            value=self.statement, expected=MeaningText, field="Acceptance statement"
        )
        RuntimeTypeValidation.require_exact(
            value=self.requirement, expected=CheckRequirement, field="Check requirement"
        )
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=DefinitionKind, field="Definition kind"
        )
        if self.kind is not DefinitionKind.ACCEPTANCE_CHECK:
            raise ValueError("Use the acceptance check definition kind")
        if type(self.predicate) not in (
            DistinctDefinitionsCheck,
            QuantityRequiredCheck,
            ManualCriterion,
        ):
            raise TypeError("Choose a supported acceptance predicate")
