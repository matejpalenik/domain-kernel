from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class PatternNotFoundError(CodedDomainError):
    """An inspected pack does not contain the requested pattern."""

    _error_code: ClassVar[str] = "pattern_not_found"

    def __init__(self) -> None:
        """Point the caller to a selector in the exact containing pack."""
        super().__init__(message="Use the exact pattern name or ID from the selected pack.")
