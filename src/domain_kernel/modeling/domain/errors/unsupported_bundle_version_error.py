from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class UnsupportedBundleVersionError(CodedDomainError):
    """The input selects a bundle version this SDK does not support."""

    _error_code: ClassVar[str] = "unsupported_bundle_version"

    def __init__(self) -> None:
        """Guide the caller to a consumer supporting the exact version."""
        super().__init__(message="Use a consumer that supports this exact bundle schema version.")
