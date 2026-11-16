"""Typed failures owned by the publication domain."""

from collections.abc import Sequence
from typing import ClassVar

from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import CodedDomainError
from domain_kernel.shared.validation import is_non_string_sequence


class PublicationBlockedError(CodedDomainError):
    """Publication readiness failed with structured diagnostics."""

    issues: tuple[Issue, ...]
    _error_code: ClassVar[str] = "publication_blocked"

    def __init__(self, *, issues: Sequence[Issue]) -> None:
        """Snapshot the issues that prevent a publication."""
        if not is_non_string_sequence(issues):
            raise TypeError("PublicationBlockedError issues must be a sequence of Issue values")
        issue_snapshot = tuple(issues)
        if any(type(issue) is not Issue for issue in issue_snapshot):
            raise TypeError("PublicationBlockedError issues must contain Issue values")
        if not issue_snapshot:
            raise ValueError("PublicationBlockedError requires at least one Issue")
        super().__init__(message="Publication is blocked by unresolved issues")
        self.issues = issue_snapshot
