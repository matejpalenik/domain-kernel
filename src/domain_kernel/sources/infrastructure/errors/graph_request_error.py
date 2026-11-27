"""A translated Microsoft Graph request failure with a status for recovery."""

from __future__ import annotations

from http import HTTPStatus
from typing import final

from domain_kernel.shared.errors.source_read_error import SourceReadError

__all__ = ["_GraphRequestError"]


@final
class _GraphRequestError(SourceReadError):
    """A Microsoft Graph request failed while reading a SharePoint source."""

    def __init__(self, *, status: int) -> None:
        """Keep the status for recovery and classify failures that may be retried."""
        self.status = status
        super().__init__(
            message=(
                "Check Graph access to the configured SharePoint drive and folder."
                if status in (401, 403)
                else "Check availability of the exact selected SharePoint item."
            ),
            retryable=status in (408, 429) or status >= HTTPStatus.INTERNAL_SERVER_ERROR,
        )
