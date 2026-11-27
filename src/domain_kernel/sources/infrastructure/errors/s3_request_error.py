"""A translated S3 request failure with a status for recovery."""

from __future__ import annotations

from typing import final

from domain_kernel.shared.errors.source_read_error import SourceReadError


@final
class S3RequestError(SourceReadError):
    """An actionable provider failure with a safe status for exact recovery."""

    def __init__(self, *, status: int, retryable: bool = False) -> None:
        """Keep provider descriptions out of SDK findings."""
        self.status = status
        super().__init__(
            message=(
                "Check the configured S3 credential and prefix permissions."
                if status in (401, 403)
                else "Check availability of the exact object in the configured S3 binding."
            ),
            retryable=retryable,
        )
