"""Typed failures owned by the projects domain."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class ProjectNotFoundError(CodedDomainError):
    """Requested project does not exist in the configured workspace."""

    _error_code: ClassVar[str] = "project_not_found"

    def __init__(
        self,
        *,
        message: str = (
            "Project lookup failed. "
            "Check the configured workspace and the exact project name or ID."
        ),
        retryable: bool = False,
    ) -> None:
        """Give the caller the workspace and selector to check."""
        super().__init__(message=message, retryable=retryable)
