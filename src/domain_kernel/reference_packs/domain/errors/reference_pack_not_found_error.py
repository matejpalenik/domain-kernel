from __future__ import annotations

from typing import ClassVar

from domain_kernel.shared.errors.coded_domain_error import CodedDomainError


class ReferencePackNotFoundError(CodedDomainError):
    """The approved catalog does not contain the exact selected version."""

    _error_code: ClassVar[str] = "reference_pack_not_found"

    def __init__(self) -> None:
        """Ask the caller to select an explicitly available pack version."""
        super().__init__(
            message="Choose an exact version from the configured reference-pack catalog."
        )
