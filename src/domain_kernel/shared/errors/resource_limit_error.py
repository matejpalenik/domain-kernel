from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class ResourceLimitError(CodedDomainError):
    """The selected resource exceeds a configured processing limit."""

    _error_code: ClassVar[str] = "resource_limit"

    def __init__(
        self,
        *,
        message: str = "Select a resource within the configured processing limit.",
    ) -> None:
        """Describe recovery without exposing source details."""
        super().__init__(message=message)
