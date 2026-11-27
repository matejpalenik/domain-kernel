from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class PublicationNotFoundError(CodedDomainError):
    """A preparation or release is unavailable in the requested workspace."""

    _error_code: ClassVar[str] = "publication_not_found"

    def __init__(self) -> None:
        """Describe the expected scope and selector."""
        super().__init__(message="Look up the exact saved publication or release in this model.")
