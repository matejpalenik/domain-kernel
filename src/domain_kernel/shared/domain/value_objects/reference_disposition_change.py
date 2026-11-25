"""Before and after state of one reviewed reference disposition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain_kernel.shared.domain.value_objects.reference_disposition import ReferenceDisposition


@dataclass(frozen=True, kw_only=True)
class ReferenceDispositionChange:
    """Before and after state of one reviewed reference disposition."""

    before: ReferenceDisposition | None
    after: ReferenceDisposition | None
