"""Failure to load a supplied schema or its dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.errors.coded_domain_error import CodedDomainError
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


class InvalidSchemaError(CodedDomainError):
    """The exact supplied schema or dependency graph could not be loaded."""

    _error_code: ClassVar[str] = "invalid_schema"
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None:
        """Preserve safe diagnostics without retaining parser payloads."""
        self.issues = SequenceValidation.snapshot_sequence(
            items=issues, item_type=Issue, field="Schema issues"
        )
        super().__init__(message="Supply the exact schema bytes and its declared dependencies.")
