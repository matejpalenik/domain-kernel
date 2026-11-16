"""Typed collision for model names."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class ModelAlreadyExistsError(CodedDomainError):
    """A model already owns the requested name in this project."""

    _error_code: ClassVar[str] = "model_already_exists"

    def __init__(
        self,
        *,
        message: str = (
            "A model already uses that name in this project. "
            "Open it by its exact name or choose an unused name."
        ),
        retryable: bool = False,
    ) -> None:
        """Explain how to open the existing model or create a distinct one."""
        super().__init__(message=message, retryable=retryable)
