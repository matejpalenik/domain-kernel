"""The requested definition revision is unavailable in this workspace."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class DefinitionNotFoundError(CodedDomainError):
    """The requested definition revision is unavailable in this workspace."""

    _error_code: ClassVar[str] = "definition_not_found"

    def __init__(self) -> None:
        """Explain which catalog to inspect before retrying."""
        super().__init__(
            message="Look up an approved definition by its exact model-local name or ID."
        )
