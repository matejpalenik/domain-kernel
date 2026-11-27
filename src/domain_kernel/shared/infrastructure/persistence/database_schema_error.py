from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class DatabaseSchemaError(CodedDomainError):
    """SQLite setup could not find or establish a compatible schema."""

    _error_code: ClassVar[str] = "database_schema"
