from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.discovery.application.errors.inference_error import InferenceError
from domain_kernel.shared.diagnostics.issue import Issue

if TYPE_CHECKING:
    from domain_kernel.discovery.application.contracts.truncated_response import TruncatedResponse


class TruncatedResponseError(InferenceError):
    """Carry the partial result privately to the response journal."""

    def __init__(self, *, response: TruncatedResponse) -> None:
        """Keep evidence of completion while giving the caller a safe diagnostic."""
        message = (
            "Inspect the incomplete provider response. "
            "Reduce the batch or increase its response limit."
        )
        super().__init__(
            message=message,
            issue=Issue(code="truncated_response", path=("response",), message=message),
        )
        self.response: TruncatedResponse = response
