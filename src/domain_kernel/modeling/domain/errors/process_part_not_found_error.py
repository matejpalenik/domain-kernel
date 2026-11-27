from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class ProcessPartNotFoundError(CodedDomainError):
    """The selected process revision does not contain the requested child."""

    _error_code: ClassVar[str] = "process_part_not_found"

    def __init__(self) -> None:
        """Point readers to the exact local selector."""
        super().__init__(message="Inspect the exact name or ID on this process revision.")
