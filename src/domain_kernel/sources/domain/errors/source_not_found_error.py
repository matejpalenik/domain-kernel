from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class SourceNotFoundError(CodedDomainError):
    """The configured reader cannot find the selected source."""

    _error_code: ClassVar[str] = "source_not_found"

    def __init__(self) -> None:
        """Guide the caller to an available reader-relative file."""
        super().__init__(message="Check the selected file in the configured reader.")
