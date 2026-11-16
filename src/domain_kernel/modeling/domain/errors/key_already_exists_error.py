"""Typed failures owned by the modeling domain."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class KeyAlreadyExistsError(CodedDomainError):
    """The key identity is repeated."""

    _error_code: ClassVar[str] = "key_already_exists"

    def __init__(
        self,
        *,
        message: str = "Choose a distinct key name and ID within this concept.",
        retryable: bool = False,
    ) -> None:
        """Explain the relevant concept-local action."""
        super().__init__(message=message, retryable=retryable)
