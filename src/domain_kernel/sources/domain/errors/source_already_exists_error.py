"""Duplicate source identity within one project."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class SourceAlreadyExistsError(CodedDomainError):
    """Creation used the exact lookup name of an existing source."""

    _error_code: ClassVar[str] = "source_already_exists"

    def __init__(self) -> None:
        """Guide callers to reopen the source or choose another name."""
        super().__init__(message="Open the existing source or choose an unused source name.")
