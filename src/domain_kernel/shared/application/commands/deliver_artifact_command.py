"""Capture the input to the durable artifact delivery use case."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from domain_kernel.shared.application.idempotency.invocation import Invocation
from domain_kernel.shared.domain.entities.audit_record import AuditRecord

if TYPE_CHECKING:
    from domain_kernel.shared.domain.entities.artifact import Artifact
    from domain_kernel.shared.domain.enums.audit_action import AuditAction
    from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
    from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
    from domain_kernel.shared.identifiers.audit_id import AuditId
    from domain_kernel.shared.json_value import JsonValue


@dataclass(frozen=True, kw_only=True)
class DeliverArtifactCommand:
    """Initiate or replay a durable artifact delivery.

    Attributes:
        intent: Canonical operation inputs that must match on replay.
        requested: Exact artifact metadata expected at the destination.
        resource: Existing source or publication captured in the audit trail.
    """

    action: AuditAction
    actor: str
    idempotency_key: str | None
    intent: JsonValue
    requested: Artifact
    resource: AuditResource

    def invocation(self) -> Invocation:
        """Bind source, location and attribution to one scope-local key."""
        return Invocation.resolve(
            project_id=self.requested.project_id,
            model_id=self.requested.model_id,
            operation=self.action.value,
            actor=self.actor,
            key=self.idempotency_key,
            intent=self.intent,
        )

    def record(
        self,
        *,
        audit_id: AuditId,
        outcome: AuditOutcome,
        parent: AuditId | None = None,
        artifact: Artifact | None = None,
    ) -> AuditRecord:
        """Capture an attributed delivery transition with its verified effect.

        Args:
            audit_id: Identity of the new audit event.
            outcome: Recorded result of the delivery attempt.
            parent: Identity of the start event when recording a later transition.
            artifact: Verified artifact for a successful delivery, when available.
        """
        return AuditRecord(
            id=audit_id,
            project_id=self.requested.project_id,
            model_id=self.requested.model_id,
            action=self.action,
            outcome=outcome,
            actor=self.actor,
            recorded_at=datetime.now(tz=UTC),
            before=(self.resource,),
            after=() if artifact is None else (artifact,),
            requested_artifact=self.requested,
            parent_id=parent,
        )
