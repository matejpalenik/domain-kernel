from __future__ import annotations

from domain_kernel.discovery.application.errors.inference_error import InferenceError
from domain_kernel.shared.diagnostics.issue import Issue


class InferenceTimeoutError(InferenceError):
    """An inference request reached its deadline before returning a response."""

    def __init__(self, *, timeout_seconds: float) -> None:
        """Retain the configured deadline for replay and diagnostics."""
        message = (
            "The inference request timed out. "
            f"The configured request limit is {timeout_seconds:g} seconds."
        )
        super().__init__(
            message=message,
            retryable=True,
            issue=Issue(code="provider_timeout", path=("response",), message=message),
        )
        self.timeout_seconds: float = timeout_seconds
