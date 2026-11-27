from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class VersionExistsError(CodedDomainError):
    """A release version already belongs to an immutable bundle."""

    _error_code: ClassVar[str] = "version_exists"

    def __init__(self) -> None:
        """Describe how to find the existing immutable version."""
        super().__init__(
            message="Open this exact released version or choose an unused version label."
        )
