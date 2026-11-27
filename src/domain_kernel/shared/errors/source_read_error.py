from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class SourceReadError(CodedDomainError):
    """The configured reader cannot safely acquire the selected source."""

    _error_code: ClassVar[str] = "source_read"
