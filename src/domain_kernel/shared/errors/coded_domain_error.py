from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.domain_kernel_error import DomainKernelError


class CodedDomainError(DomainKernelError):
    """Base for domain exceptions whose code is fixed by their type."""

    _error_code: ClassVar[str]

    def __init__(self, *, message: str, retryable: bool = False) -> None:
        """Initialize the exception with its fixed code and message."""
        super().__init__(message=message, code=self._error_code, retryable=retryable)
