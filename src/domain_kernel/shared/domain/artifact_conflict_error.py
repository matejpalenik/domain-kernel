"""A destination already identifies a different immutable artifact."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class ArtifactConflictError(CodedDomainError):
    """The destination's bytes or metadata differ from the requested artifact."""

    _error_code: ClassVar[str] = "artifact_conflict"

    def __init__(self) -> None:
        """Guide the caller to an unused destination or a matching retry."""
        super().__init__(
            message="Choose a new artifact key or retry with the exact bytes and metadata."
        )
