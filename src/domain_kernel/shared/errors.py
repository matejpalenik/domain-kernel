"""Cross-domain exception base and configuration failures."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.validation import is_non_string_sequence, snapshot_sequence

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


class IdempotencyConflictError(CodedDomainError):
    """A durable request key was already claimed for a different invocation."""

    _error_code: ClassVar[str] = "idempotency_conflict"

    def __init__(self) -> None:
        """Describe recovery without exposing the actor, key, or request body."""
        super().__init__(
            message="Replay with the original request and actor, or use a new key for new work.",
        )


class OperationInProgressError(CodedDomainError):
    """A matching durable request already has an active lease."""

    _error_code: ClassVar[str] = "operation_in_progress"

    def __init__(self) -> None:
        """Tell the caller how to recover the original outcome."""
        super().__init__(
            message="The operation is active. Retry later with the same request and key.",
            retryable=True,
        )


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


class ScopeMismatchError(CodedDomainError):
    """A supplied identity belongs to a different workspace."""

    _error_code: ClassVar[str] = "scope_mismatch"

    def __init__(self) -> None:
        """Tell the caller which scope to reopen."""
        super().__init__(message="Use an exact snapshot from the selected workspace.")


class VersionExistsError(CodedDomainError):
    """A release version already belongs to an immutable bundle."""

    _error_code: ClassVar[str] = "version_exists"

    def __init__(self) -> None:
        """Describe how to find the existing immutable version."""
        super().__init__(
            message="Open this exact released version or choose an unused version label."
        )


class PublicationNotFoundError(CodedDomainError):
    """A preparation or release is unavailable in the requested workspace."""

    _error_code: ClassVar[str] = "publication_not_found"

    def __init__(self) -> None:
        """Describe the expected scope and selector."""
        super().__init__(message="Look up the exact saved publication or release in this model.")


class UnsupportedBundleVersionError(CodedDomainError):
    """The input selects a bundle version this SDK does not support."""

    _error_code: ClassVar[str] = "unsupported_bundle_version"

    def __init__(self) -> None:
        """Guide the caller to a consumer supporting the exact version."""
        super().__init__(message="Use a consumer that supports this exact bundle schema version.")


class InvalidBundleError(CodedDomainError):
    """Complete bundle structure or integrity checks failed."""

    _error_code: ClassVar[str] = "invalid_bundle"
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None:
        """Retain safe structured issues without the supplied payload."""
        self.issues = snapshot_sequence(items=issues, item_type=Issue, field="Bundle issues")
        super().__init__(message="Load an intact bundle from the exact published version.")
