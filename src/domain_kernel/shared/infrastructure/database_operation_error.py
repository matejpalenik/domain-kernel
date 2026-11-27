from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class DatabaseOperationError(CodedDomainError):
    """PostgreSQL could not complete an operation or establish its outcome."""

    _error_code: ClassVar[str] = "database_operation"
