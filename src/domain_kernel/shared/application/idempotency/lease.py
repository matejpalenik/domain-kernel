from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


from domain_kernel.shared.application.idempotency.operation_validation import OperationValidation


@dataclass(frozen=True, kw_only=True)
class Lease:
    """Time-limited commit authority issued to one operation worker."""

    token: str
    owner: str
    expires_at: datetime

    def __post_init__(self) -> None:
        """Reject empty holders and ambiguous timestamps."""
        OperationValidation.require_nonblank(value=self.token, field="Lease token")
        OperationValidation.require_nonblank(value=self.owner, field="Lease owner")

        if self.expires_at.utcoffset() is None:
            raise ValueError("Lease expiry must include a time zone")
