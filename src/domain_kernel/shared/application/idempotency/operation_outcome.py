from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.application.idempotency.operation_validation import OperationValidation


@dataclass(frozen=True, kw_only=True)
class OperationOutcome:
    """Detached identity of the exact result committed for a durable request."""

    resource_kind: str
    resource_id: str
    resource_version: str | None = None

    def __post_init__(self) -> None:
        """Require a resolved resource identity."""
        OperationValidation.require_nonblank(value=self.resource_kind, field="Resource kind")
        OperationValidation.require_nonblank(value=self.resource_id, field="Resource ID")

        if self.resource_version is not None:
            OperationValidation.require_nonblank(
                value=self.resource_version, field="Resource version"
            )
