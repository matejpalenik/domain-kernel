"""Typed failures owned by the modeling domain."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class AttributeNotFoundError(CodedDomainError):
    """The attribute lookup has no match."""

    _error_code: ClassVar[str] = "attribute_not_found"

    def __init__(
        self,
        *,
        message: str = "Check the exact attribute name or ID in the inspected concept.",
        retryable: bool = False,
    ) -> None:
        """Explain the relevant concept-local action."""
        super().__init__(message=message, retryable=retryable)
