from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class OperationInProgressError(CodedDomainError):
    """A matching durable request already has an active lease."""

    _error_code: ClassVar[str] = "operation_in_progress"

    def __init__(self) -> None:
        """Tell the caller how to recover the original outcome."""
        super().__init__(
            message="The operation is active. Retry later with the same request and key.",
            retryable=True,
        )
