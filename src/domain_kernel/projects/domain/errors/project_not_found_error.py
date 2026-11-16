"""Typed failures owned by the projects domain."""

from typing import ClassVar

from domain_kernel.shared.errors import CodedDomainError


class ProjectNotFoundError(CodedDomainError):
    """Requested project does not exist in the configured workspace."""

    _error_code: ClassVar[str] = "project_not_found"
