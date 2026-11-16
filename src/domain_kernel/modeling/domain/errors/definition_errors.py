"""Typed lookup and identity conflicts in a model's definition catalog."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class DefinitionNotFoundError(CodedDomainError):
    """The requested definition revision is unavailable in this workspace."""

    _error_code: ClassVar[str] = "definition_not_found"

    def __init__(self) -> None:
        """Explain which catalog to inspect before retrying."""
        super().__init__(
            message="Look up an approved definition by its exact model-local name or ID."
        )


class DefinitionAlreadyExistsError(CodedDomainError):
    """A pending or approved definition already reserves this lookup name."""

    _error_code: ClassVar[str] = "definition_already_exists"

    def __init__(self) -> None:
        """Explain how to recover with the existing reservation."""
        super().__init__(
            message="Inspect the existing definition or pending case, or choose a new name."
        )


class DefinitionKindMismatchError(CodedDomainError):
    """The exact inspected definition has a different kind from the requested view."""

    _error_code: ClassVar[str] = "definition_kind_mismatch"

    def __init__(self) -> None:
        """Explain how to inspect the definition's kind."""
        super().__init__(
            message="Use the general definition lookup to inspect this definition's kind."
        )
