"""Cross-domain exception base and configuration failures."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.validation import is_non_string_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence


def _validated_nonempty_string(value: object, *, name: str) -> str:
    if type(value) is not str:
        message = f"{name} must be a string"
        raise TypeError(message)
    if not value:
        message = f"{name} must be a nonempty string"
        raise ValueError(message)
    return value


def _validated_bool(value: object, *, name: str) -> bool:
    if type(value) is not bool:
        message = f"{name} must be a bool"
        raise TypeError(message)
    return value


class DomainKernelError(Exception):
    """Base for typed SDK failures with stable machine-readable codes."""

    code: str
    retryable: bool

    def __init__(self, *, message: str, code: str, retryable: bool = False) -> None:
        """Initialize a sanitized message and stable failure metadata."""
        message = _validated_nonempty_string(message, name="Error message")
        code = _validated_nonempty_string(code, name="Error code")
        retryable = _validated_bool(retryable, name="retryable")
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class CodedDomainError(DomainKernelError):
    """Base for domain exceptions whose code is fixed by their type."""

    _error_code: ClassVar[str]

    def __init__(self, *, message: str, retryable: bool = False) -> None:
        """Initialize the exception with its fixed code and message."""
        super().__init__(message=message, code=self._error_code, retryable=retryable)


class ConfigurationError(DomainKernelError):
    """Configuration validation failure with detached structured diagnostics."""

    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None:
        """Snapshot sanitized issues without retaining provider or parser exceptions."""
        if not is_non_string_sequence(issues):
            raise TypeError("ConfigurationError issues must be a sequence of Issue values")
        issue_snapshot = tuple(issues)
        if any(type(issue) is not Issue for issue in issue_snapshot):
            raise TypeError("ConfigurationError issues must contain Issue values")
        if not issue_snapshot:
            raise ValueError("ConfigurationError requires at least one Issue")
        message = "; ".join(issue.message for issue in issue_snapshot)
        super().__init__(message=message, code="configuration_error")
        self.issues = issue_snapshot


class StaleStateError(CodedDomainError):
    """Operation rejected because the expected state is no longer current."""

    _error_code: ClassVar[str] = "stale_state"

    def __init__(
        self,
        *,
        message: str = (
            "The operation used an out-of-date snapshot. "
            "Reload and inspect the current state before preparing a new request."
        ),
        retryable: bool = False,
    ) -> None:
        """Tell the caller how to recover from stale input."""
        super().__init__(message=message, retryable=retryable)


class MissingCapabilityError(CodedDomainError):
    """The operation requires a capability the client has not configured."""

    _error_code: ClassVar[str] = "missing_capability"

    def __init__(
        self,
        *,
        message: str = (
            "The operation requires an unconfigured capability. "
            "Configure the required capability before trying again."
        ),
        retryable: bool = False,
    ) -> None:
        """Tell the caller to configure the required capability."""
        super().__init__(message=message, retryable=retryable)
