"""Evaluate an inspected case with an explicit action inside a plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel.review.domain.decisions import (
    Accept,
    ApproveLocalExtension,
    ContentChangeAction,
    EditDefinition,
    Exclude,
    MapToDefinition,
    MapToReference,
    Reject,
)
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.domain.operations.map_to_planned_definition import MapToPlannedDefinition
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class IncludeCase:
    """Evaluate an inspected case with an explicit action inside a plan."""

    case_id: ReviewCaseId
    expected_version: int
    decision: ContentChangeAction | Reject | MapToPlannedDefinition
    kind: Literal["include_case"] = "include_case"

    def __post_init__(self) -> None:
        """Validate the inspected version and one applicable leaf action."""
        RuntimeTypeValidation.require_exact(
            value=self.case_id, expected=ReviewCaseId, field="Case identity"
        )
        RuntimeTypeValidation.require_exact(
            value=self.expected_version, expected=int, field="Case version"
        )
        if self.expected_version < 1:
            raise ValueError("Case version must be positive")
        if type(self.decision) not in (
            Accept,
            EditDefinition,
            Reject,
            MapToDefinition,
            MapToReference,
            ApproveLocalExtension,
            Exclude,
            MapToPlannedDefinition,
        ):
            raise TypeError("Choose an explicit leaf decision")
        RuntimeTypeValidation.require_exact(value=self.kind, expected=str, field="Plan action kind")
        if self.kind != "include_case":
            raise ValueError("Use the include case operation kind")
