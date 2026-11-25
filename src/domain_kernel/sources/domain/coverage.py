"""Explicit coverage of a pinned source capture."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.sources.domain.parsed import require_locator

if TYPE_CHECKING:
    from domain_kernel.sources.domain.parsed import EvidenceLocator


class CoverageStatus(StrEnum):
    """The disposition of a selected source unit."""

    PROCESSED = "processed"
    EMPTY = "empty"
    UNREADABLE = "unreadable"
    UNSUPPORTED = "unsupported"
    DEFERRED = "deferred"


@dataclass(frozen=True, kw_only=True)
class CoverageUnit:
    """Account for one addressable unit independently of its evidence citations."""

    locator: EvidenceLocator
    status: CoverageStatus

    def __post_init__(self) -> None:
        """Require a typed disposition and an addressable source unit."""
        require_locator(locator=self.locator)
        RuntimeTypeValidation.require_exact(
            value=self.status, expected=CoverageStatus, field="Coverage status"
        )
