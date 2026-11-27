from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class UnsupportedReferencePackVersionError(CodedDomainError):
    """The requested portable pack format lacks a registered codec."""

    _error_code: ClassVar[str] = "unsupported_reference_pack_version"

    def __init__(self) -> None:
        """Explain how to load an unsupported format version."""
        super().__init__(message="Use a consumer that supports this reference-pack schema version.")
