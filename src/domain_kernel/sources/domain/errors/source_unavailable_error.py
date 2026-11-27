"""An exact source capture is unavailable."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class SourceUnavailableError(CodedDomainError):
    """The exact requested host content or original bytes could not be obtained."""

    _error_code: ClassVar[str] = "source_unavailable"

    def __init__(self) -> None:
        """Describe recovery without exposing provider details."""
        super().__init__(message="Make the exact captured source available and try again.")
