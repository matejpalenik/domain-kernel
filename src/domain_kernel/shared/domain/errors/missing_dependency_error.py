"""An optional SDK adapter is unavailable."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class MissingDependencyError(CodedDomainError):
    """An optional SDK adapter is unavailable."""

    _error_code: ClassVar[str] = "missing_dependency"

    def __init__(self, *, message: str = "Install the SDK's ontology extra.") -> None:
        """Identify the missing extra and how to install it."""
        super().__init__(message=message)
