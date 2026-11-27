"""Typed failures owned by the modeling domain."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class ModelNotFoundError(CodedDomainError):
    """Requested model does not exist in the project scope."""

    _error_code: ClassVar[str] = "model_not_found"

    def __init__(
        self,
        *,
        message: str = "Model lookup failed. Check the project and the exact model name or ID.",
        retryable: bool = False,
    ) -> None:
        """Give the caller the scope and selector to check."""
        super().__init__(message=message, retryable=retryable)
