"""The selected artifact or its dependencies fail exact ontology validation."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class InvalidOntologyError(CodedDomainError):
    """The selected artifact or its dependencies fail exact ontology validation."""

    _error_code: ClassVar[str] = "invalid_ontology"

    def __init__(
        self,
        *,
        message: str = "Supply exact ontology bytes, the declared graph and all pinned resources.",
    ) -> None:
        """Describe the invalid ontology input and how to correct it."""
        super().__init__(message=message)
