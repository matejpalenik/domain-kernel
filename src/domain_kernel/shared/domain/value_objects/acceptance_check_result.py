"""A predicate outcome bound to its candidate and evaluator version."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.enums.check_outcome import CheckOutcome
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


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
