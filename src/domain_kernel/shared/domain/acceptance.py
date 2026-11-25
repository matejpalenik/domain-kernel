"""Bounded, explicit model acceptance predicates and their captured results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.data_shapes import require_definition_reference
from domain_kernel.shared.domain.model_values import MeaningText
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference


@unique
class CheckRequirement(StrEnum):
    """Whether the review requires verified executable success."""

    REQUIRED = "required"
    ADVISORY = "advisory"


@unique
class CheckOutcome(StrEnum):
    """Outcome of one acceptance predicate on a captured candidate."""

    PASS = "pass"  # noqa: S105 - Acceptance outcome wire value.
    FAIL = "fail"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass(frozen=True, kw_only=True)
class DistinctDefinitionsCheck:
    """Require two resolved identities to be distinct."""

    left: DefinitionReference
    right: DefinitionReference
    kind: Literal["distinct_definitions"] = "distinct_definitions"

    def __post_init__(self) -> None:
        """Bind both exact references without resolving them."""
        require_definition_reference(value=self.left, field="Left definition")
        require_definition_reference(value=self.right, field="Right definition")
        if self.kind != "distinct_definitions":
            raise ValueError("Use the distinct definitions predicate kind")


@dataclass(frozen=True, kw_only=True)
class QuantityRequiredCheck:
    """Require a valid quantity and unit vocabulary on one structured value."""

    structure: DefinitionReference
    kind: Literal["quantity_required"] = "quantity_required"

    def __post_init__(self) -> None:
        """Bind the exact structured value reference."""
        require_definition_reference(value=self.structure, field="Structured value")
        if self.kind != "quantity_required":
            raise ValueError("Use the quantity required predicate kind")


@dataclass(frozen=True, kw_only=True)
class ManualCriterion:
    """Preserve an authored criterion that requires human judgement."""

    kind: Literal["manual_criterion"] = "manual_criterion"

    def __post_init__(self) -> None:
        """Check the closed manual predicate discriminator."""
        if self.kind != "manual_criterion":
            raise ValueError("Use the manual criterion predicate kind")


type AcceptancePredicate = DistinctDefinitionsCheck | QuantityRequiredCheck | ManualCriterion


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


@dataclass(frozen=True, kw_only=True)
class AcceptanceCheckResult:
    """A predicate outcome bound to its candidate and evaluator version."""

    definition_id: DefinitionId
    candidate_hash: ContentHash
    outcome: CheckOutcome
    evaluator_fingerprint: ContentHash
    issues: Sequence[Issue] = ()

    def __post_init__(self) -> None:
        """Detach diagnostics and enforce nominal result binding."""
        RuntimeTypeValidation.require_exact(
            value=self.definition_id, expected=DefinitionId, field="Acceptance check ID"
        )
        RuntimeTypeValidation.require_exact(
            value=self.candidate_hash, expected=ContentHash, field="Candidate hash"
        )
        RuntimeTypeValidation.require_exact(
            value=self.outcome, expected=CheckOutcome, field="Acceptance outcome"
        )
        RuntimeTypeValidation.require_exact(
            value=self.evaluator_fingerprint, expected=ContentHash, field="Evaluator hash"
        )
        object.__setattr__(
            self,
            "issues",
            SequenceValidation.snapshot_sequence(
                items=self.issues, item_type=Issue, field="Acceptance issues"
            ),
        )
