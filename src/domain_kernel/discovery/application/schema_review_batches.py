"""The issued question scope and its original evidence positions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain_kernel.discovery.application import schema_facets


@dataclass(frozen=True, kw_only=True)
class ReviewBatch:
    """The fixed question and original evidence positions issued together."""

    id: int
    facets: tuple[schema_facets.Facet, ...]
    selected: tuple[int, ...]
