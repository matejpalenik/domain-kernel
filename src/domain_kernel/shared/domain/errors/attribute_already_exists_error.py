"""Typed failures owned by the modeling domain."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class AttributeAlreadyExistsError(CodedDomainError):
    """The attribute identity is repeated."""

    _error_code: ClassVar[str] = "attribute_already_exists"

    def __init__(
        self,
        *,
        message: str = "Choose a distinct attribute name and ID within this definition.",
        retryable: bool = False,
    ) -> None:
        """Explain the relevant concept-local action."""
        super().__init__(message=message, retryable=retryable)
