from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError

if TYPE_CHECKING:
    from domain_kernel.shared.diagnostics.issue import Issue


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
