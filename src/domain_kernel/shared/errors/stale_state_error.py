from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class StaleStateError(CodedDomainError):
    """Operation rejected because the expected state is no longer current."""

    _error_code: ClassVar[str] = "stale_state"

    def __init__(
        self,
        *,
        message: str = (
            "The operation used an out-of-date snapshot. "
            "Reload and inspect the current state before preparing a new request."
        ),
        retryable: bool = False,
    ) -> None:
        """Tell the caller how to recover from stale input."""
        super().__init__(message=message, retryable=retryable)
