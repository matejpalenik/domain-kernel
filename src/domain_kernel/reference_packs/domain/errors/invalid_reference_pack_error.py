from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class InvalidReferencePackError(CodedDomainError):
    """A reference pack has invalid structure, closure or integrity."""

    _error_code: ClassVar[str] = "invalid_reference_pack"
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None:
        """Retain only sanitized structural and integrity issues."""
        self.issues = SequenceValidation.snapshot_sequence(
            items=issues, item_type=Issue, field="Pack issues"
        )
        super().__init__(message="Load the exact intact reference pack from its approved source.")
