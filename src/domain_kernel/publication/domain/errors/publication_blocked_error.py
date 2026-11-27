"""Typed failures owned by the publication domain."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.errors.coded_domain_error import CodedDomainError
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.publications import Publication


class PublicationBlockedError(CodedDomainError):
    """Publication readiness failed with structured diagnostics."""

    issues: tuple[Issue, ...]
    publication: Publication | None
    _error_code: ClassVar[str] = "publication_blocked"

    def __init__(
        self, *, issues: Sequence[Issue] | None = None, publication: Publication | None = None
    ) -> None:
        """Snapshot the issues that prevent a publication."""
        self.publication = publication
        if publication is not None:
            if issues is not None:
                raise TypeError("Supply the publication's captured blockers")
            issues = publication.blockers
        if issues is None:
            raise TypeError("Supply a blocked publication or its issues")
        if not SequenceValidation.is_non_string_sequence(value=issues):
            raise TypeError("PublicationBlockedError issues must be a sequence of Issue values")
        issue_snapshot = tuple(issues)
        if any(type(issue) is not Issue for issue in issue_snapshot):
            raise TypeError("PublicationBlockedError issues must contain Issue values")
        if not issue_snapshot:
            raise ValueError("PublicationBlockedError requires at least one Issue")
        super().__init__(message="Publication is blocked by unresolved issues")
        self.issues = issue_snapshot
