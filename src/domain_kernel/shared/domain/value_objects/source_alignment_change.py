"""Before and after state of one reviewed source alignment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain_kernel.shared.domain.value_objects.source_alignment import SourceAlignment


@dataclass(frozen=True, kw_only=True)
class SourceAlignmentChange:
    """Before and after state of one reviewed source alignment."""

    before: SourceAlignment | None
    after: SourceAlignment | None
