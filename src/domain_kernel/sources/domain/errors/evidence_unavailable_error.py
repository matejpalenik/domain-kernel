"""The exact requested evidence citation cannot be retrieved."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class EvidenceUnavailableError(CodedDomainError):
    """The inspected citation is missing or its locator cannot be resolved."""

    _error_code: ClassVar[str] = "evidence_unavailable"

    def __init__(self) -> None:
        """Guide the caller to the captured citation."""
        super().__init__(message="Inspect the stored citation and its exact source revision.")
