"""The exact inspected definition has a different kind from the requested view."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class DefinitionKindMismatchError(CodedDomainError):
    """The exact inspected definition has a different kind from the requested view."""

    _error_code: ClassVar[str] = "definition_kind_mismatch"

    def __init__(self) -> None:
        """Explain how to inspect the definition's kind."""
        super().__init__(
            message="Use the general definition lookup to inspect this definition's kind."
        )
