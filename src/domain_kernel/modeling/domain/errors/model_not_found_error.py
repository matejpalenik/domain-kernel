"""Typed failures owned by the modeling domain."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class ModelNotFoundError(CodedDomainError):
    """Requested model does not exist in the project scope."""

    _error_code: ClassVar[str] = "model_not_found"
