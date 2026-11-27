"""Version or digest of an exact retained resource."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.types.audit_resource_id import (
    AUDIT_RESOURCE_TYPES,
    AuditResourceId,
)
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class AuditResource:
    """Version or digest of an exact retained resource."""

    resource_id: AuditResourceId
    revision: int | None
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Require a recognized nominal resource and exact hash."""
        if type(self.resource_id) not in AUDIT_RESOURCE_TYPES:
            raise TypeError("Audit resources require a supported nominal resource identity")
        RuntimeTypeValidation.require_exact(
            value=self.content_hash, expected=ContentHash, field="Audit resource hash"
        )

        if self.revision is not None:
            RuntimeTypeValidation.require_exact(
                value=self.revision, expected=int, field="Audit resource revision"
            )
            if self.revision < 0:
                raise ValueError("Audit resource revision must be nonnegative")
