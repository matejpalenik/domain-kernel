"""A pending or approved definition already reserves this lookup name."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class DefinitionAlreadyExistsError(CodedDomainError):
    """A pending or approved definition already reserves this lookup name."""

    _error_code: ClassVar[str] = "definition_already_exists"

    def __init__(self) -> None:
        """Explain how to recover with the existing reservation."""
        super().__init__(
            message="Inspect the existing definition or pending case, or choose a new name."
        )
