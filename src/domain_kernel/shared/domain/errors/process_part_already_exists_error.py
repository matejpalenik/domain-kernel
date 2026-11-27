from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class ProcessPartAlreadyExistsError(CodedDomainError):
    """An owning process or decision already uses this child name or ID."""

    _error_code: ClassVar[str] = "process_part_already_exists"

    def __init__(self) -> None:
        """Guide authors to inspect or change the conflicting name."""
        super().__init__(message="Use distinct part names and IDs in the owning definition.")
