from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from domain_kernel.shared.domain.entities.artifact import Artifact


@dataclass(frozen=True, kw_only=True)
class DeliveryReceipt:
    """The exact verified artifact and its committed acknowledgement time."""

    artifact: Artifact
    recorded_at: datetime
