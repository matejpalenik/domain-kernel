"""Typed failures owned by the review domain."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import CodedDomainError
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


class InvalidDecisionError(CodedDomainError):
    """Review decision is invalid for the case's current state."""

    _error_code: ClassVar[str] = "invalid_decision"

    def __init__(
        self,
        *,
        message: str,
        retryable: bool = False,
        issues: Sequence[Issue] = (),
    ) -> None:
        """Retain actionable findings from the inspected review when available."""
        self.issues: tuple[Issue, ...] = SequenceValidation.snapshot_sequence(
            items=issues,
            item_type=Issue,
            field="Issues",
        )
        super().__init__(message=message, retryable=retryable)
