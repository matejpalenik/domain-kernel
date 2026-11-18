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


class ProcessPartAlreadyExistsError(CodedDomainError):
    """An owning process or decision already uses this child name or ID."""

    _error_code: ClassVar[str] = "process_part_already_exists"

    def __init__(self) -> None:
        """Guide authors to inspect or change the conflicting name."""
        super().__init__(message="Use distinct part names and IDs in the owning definition.")


class ProcessPartNotFoundError(CodedDomainError):
    """The selected process revision does not contain the requested child."""

    _error_code: ClassVar[str] = "process_part_not_found"

    def __init__(self) -> None:
        """Point readers to the exact local selector."""
        super().__init__(message="Inspect the exact name or ID on this process revision.")


class InvalidReferencePackError(CodedDomainError):
    """A reference pack has invalid structure, closure or integrity."""

    _error_code: ClassVar[str] = "invalid_reference_pack"
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None:
        """Retain only sanitized structural and integrity issues."""
        self.issues = snapshot_sequence(items=issues, item_type=Issue, field="Pack issues")
        super().__init__(message="Load the exact intact reference pack from its approved source.")


class UnsupportedReferencePackVersionError(CodedDomainError):
    """The requested portable pack format lacks a registered codec."""

    _error_code: ClassVar[str] = "unsupported_reference_pack_version"

    def __init__(self) -> None:
        """Explain how to load an unsupported format version."""
        super().__init__(message="Use a consumer that supports this reference-pack schema version.")


class PatternNotFoundError(CodedDomainError):
    """An inspected pack does not contain the requested pattern."""

    _error_code: ClassVar[str] = "pattern_not_found"

    def __init__(self) -> None:
        """Point the caller to a selector in the exact containing pack."""
        super().__init__(message="Use the exact pattern name or ID from the selected pack.")


class ReferencePackNotFoundError(CodedDomainError):
    """The approved catalog does not contain the exact selected version."""

    _error_code: ClassVar[str] = "reference_pack_not_found"

    def __init__(self) -> None:
        """Ask the caller to select an explicitly available pack version."""
        super().__init__(
            message="Choose an exact version from the configured reference-pack catalog."
        )


class SourceNotFoundError(CodedDomainError):
    """The configured reader cannot find the selected source."""

    _error_code: ClassVar[str] = "source_not_found"

    def __init__(self) -> None:
        """Guide the caller to an available reader-relative file."""
        super().__init__(message="Check the selected file in the configured reader.")


class InferenceError(CodedDomainError):
    """An inference attempt failed before a typed draft could be returned."""

    _error_code: ClassVar[str] = "inference_failed"

    def __init__(
        self,
        *,
        message: str = "Inspect the configured inference provider and its output.",
        retryable: bool = False,
        issue: Issue | None = None,
    ) -> None:
        """Keep actionable recovery metadata without leaking provider data."""
        super().__init__(message=message, retryable=retryable)
        self.issue: Issue | None = issue


class SourceReadError(CodedDomainError):
    """The configured reader cannot safely acquire the selected source."""

    _error_code: ClassVar[str] = "source_read"


class ResourceLimitError(CodedDomainError):
    """The selected resource exceeds a configured processing limit."""

    _error_code: ClassVar[str] = "resource_limit"

    def __init__(
        self,
        *,
        message: str = "Select a resource within the configured processing limit.",
    ) -> None:
        """Describe recovery without exposing source details."""
        super().__init__(message=message)
