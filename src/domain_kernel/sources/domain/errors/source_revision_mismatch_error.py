"""The selected bytes differ from an inspected acquisition."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class SourceRevisionMismatchError(CodedDomainError):
    """An exact content or provider guard no longer matches the opened source."""

    _error_code: ClassVar[str] = "source_revision_mismatch"

    def __init__(self) -> None:
        """Guide callers to the original pinned bytes."""
        super().__init__(message="Provide the original bytes and exact source revision.")
