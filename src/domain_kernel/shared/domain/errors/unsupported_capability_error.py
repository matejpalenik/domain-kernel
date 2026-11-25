"""The configured adapter cannot preserve the requested semantics."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class UnsupportedCapabilityError(CodedDomainError):
    """The configured adapter cannot preserve the requested semantics."""

    _error_code: ClassVar[str] = "unsupported_capability"

    def __init__(
        self, *, message: str = "Select an ontology adapter that supports this syntax."
    ) -> None:
        """Explain which capability the selected adapter lacks."""
        super().__init__(message=message)
