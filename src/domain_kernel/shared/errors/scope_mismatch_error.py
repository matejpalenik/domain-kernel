from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class ScopeMismatchError(CodedDomainError):
    """A supplied identity belongs to a different workspace."""

    _error_code: ClassVar[str] = "scope_mismatch"

    def __init__(self) -> None:
        """Tell the caller which scope to reopen."""
        super().__init__(message="Use an exact snapshot from the selected workspace.")
