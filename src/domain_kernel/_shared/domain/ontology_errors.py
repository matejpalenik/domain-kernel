"""Typed ontology failures with safe recovery directions."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class InvalidOntologyError(CodedDomainError):
    """The selected artifact or its dependencies fail exact ontology validation."""

    _error_code: ClassVar[str] = "invalid_ontology"

    def __init__(
        self,
        *,
        message: str = "Supply exact ontology bytes, the declared graph and all pinned resources.",
    ) -> None:
        super().__init__(message=message)


class MissingDependencyError(CodedDomainError):
    """An optional SDK adapter is unavailable."""

    _error_code: ClassVar[str] = "missing_dependency"

    def __init__(self, *, message: str = "Install the SDK's ontology extra.") -> None:
        super().__init__(message=message)


class UnsupportedCapabilityError(CodedDomainError):
    """The configured adapter cannot preserve the requested semantics."""

    _error_code: ClassVar[str] = "unsupported_capability"

    def __init__(
        self, *, message: str = "Select an ontology adapter that supports this syntax."
    ) -> None:
        super().__init__(message=message)
