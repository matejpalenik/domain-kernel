"""Typed collision for project names."""

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class ProjectAlreadyExistsError(CodedDomainError):
    """A project already owns the requested name in this workspace."""

    _error_code: ClassVar[str] = "project_already_exists"

    def __init__(
        self,
        *,
        message: str = (
            "A project already uses that name in this workspace. "
            "Open it by its exact name or choose an unused name."
        ),
        retryable: bool = False,
    ) -> None:
        """Explain how to open the existing project or create a distinct one."""
        super().__init__(message=message, retryable=retryable)
