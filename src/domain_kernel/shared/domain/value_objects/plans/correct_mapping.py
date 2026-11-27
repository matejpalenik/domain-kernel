"""Reopen selected occurrences and review the new meaning atomically."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.review.domain.decisions import (
    ApproveLocalExtension,
    Exclude,
    MapToDefinition,
    MapToReference,
)
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.domain.value_objects.plans.map_to_planned_definition import (
    MapToPlannedDefinition,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.types.mapping_correction_action import MappingCorrectionAction


@dataclass(frozen=True, kw_only=True)
class CorrectMapping:
    """Reopen selected occurrences and review the new meaning atomically."""

    case_id: ReviewCaseId
    expected_version: int
    decision: MappingCorrectionAction
    proposal_ids: Sequence[ProposalId] | None
    reason: str
    kind: Literal["correct_mapping"] = "correct_mapping"

    def __post_init__(self) -> None:
        """Retain exact case, action and optional subset of occurrences."""
        RuntimeTypeValidation.require_exact(
            value=self.case_id, expected=ReviewCaseId, field="Case identity"
        )
        RuntimeTypeValidation.require_exact(
            value=self.expected_version, expected=int, field="Case version"
        )
        if self.expected_version < 1:
            raise ValueError("Case version must be positive")

        if type(self.decision) not in (
            MapToDefinition,
            MapToReference,
            ApproveLocalExtension,
            Exclude,
            MapToPlannedDefinition,
        ):
            raise TypeError("Choose an explicit mapping correction")

        TextValidation.require_text(value=self.reason, field="Correction reason")

        RuntimeTypeValidation.require_exact(value=self.kind, expected=str, field="Plan action kind")
        if self.kind != "correct_mapping":
            raise ValueError("Use the mapping correction action")

        if self.proposal_ids is not None:
            occurrences = SequenceValidation.snapshot_sequence(
                items=self.proposal_ids,
                item_type=ProposalId,
                field="Selected occurrences",
            )
            if not occurrences or len(set(occurrences)) != len(occurrences):
                raise ValueError("Select distinct source occurrences")

            object.__setattr__(self, "proposal_ids", occurrences)
