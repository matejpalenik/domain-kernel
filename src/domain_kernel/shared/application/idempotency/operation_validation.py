"""Validate fields shared by durable operation values."""

from __future__ import annotations

from typing import final


@final
class OperationValidation:
    """Validate fields that identify and own an idempotent operation."""

    @staticmethod
    def require_nonblank(*, value: object, field: str) -> None:
        """Require an exact string with at least one non-whitespace character."""
        if type(value) is not str:
            message = f"{field} must be an exact string"
            raise TypeError(message)

        if not value.strip():
            message = f"{field} must not be blank"
            raise ValueError(message)
