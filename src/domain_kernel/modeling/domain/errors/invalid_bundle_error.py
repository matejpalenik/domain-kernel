from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class InvalidBundleError(CodedDomainError):
    """Complete bundle structure or integrity checks failed."""

    _error_code: ClassVar[str] = "invalid_bundle"
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None:
        """Retain safe structured issues without the supplied payload."""
        self.issues = SequenceValidation.snapshot_sequence(
            items=issues, item_type=Issue, field="Bundle issues"
        )
        super().__init__(message="Load an intact bundle from the exact published version.")
