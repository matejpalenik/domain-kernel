from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class IdempotencyConflictError(CodedDomainError):
    """A durable request key was already claimed for a different invocation."""

    _error_code: ClassVar[str] = "idempotency_conflict"

    def __init__(self) -> None:
        """Describe recovery without exposing the actor, key, or request body."""
        super().__init__(
            message="Replay with the original request and actor, or use a new key for new work.",
        )
