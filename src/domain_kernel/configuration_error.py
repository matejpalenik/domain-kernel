from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

from domain_kernel.shared.errors.domain_kernel_error import DomainKernelError


class ConfigurationError(DomainKernelError):
    """Configuration validation failure with detached structured diagnostics."""

    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None:
        """Snapshot sanitized issues without retaining provider or parser exceptions."""
        if not SequenceValidation.is_non_string_sequence(value=issues):
            raise TypeError("ConfigurationError issues must be a sequence of Issue values")

        issue_snapshot = tuple(issues)
        if any(type(issue) is not Issue for issue in issue_snapshot):
            raise TypeError("ConfigurationError issues must contain Issue values")
        if not issue_snapshot:
            raise ValueError("ConfigurationError requires at least one Issue")

        message = "; ".join(issue.message for issue in issue_snapshot)
        super().__init__(message=message, code="configuration_error")
        self.issues = issue_snapshot
