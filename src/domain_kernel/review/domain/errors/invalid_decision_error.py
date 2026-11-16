"""Typed failures owned by the review domain."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class InvalidDecisionError(CodedDomainError):
    """Review decision is invalid for the case's current state."""

    _error_code: ClassVar[str] = "invalid_decision"
