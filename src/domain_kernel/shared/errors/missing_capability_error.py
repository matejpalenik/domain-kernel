from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class MissingCapabilityError(CodedDomainError):
    """The operation requires a capability the client has not configured."""

    _error_code: ClassVar[str] = "missing_capability"

    def __init__(
        self,
        *,
        message: str = (
            "The operation requires an unconfigured capability. "
            "Configure the required capability before trying again."
        ),
        retryable: bool = False,
    ) -> None:
        """Tell the caller to configure the required capability."""
        super().__init__(message=message, retryable=retryable)
