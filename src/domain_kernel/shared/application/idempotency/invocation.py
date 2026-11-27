from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self
from uuid import uuid4

from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.identifiers.model_id import ModelId
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.identifiers.audit_id import AuditId
    from domain_kernel.shared.identifiers.content_hash import ContentHash
    from domain_kernel.shared.json_value import JsonValue

from domain_kernel.shared.application.idempotency.operation_validation import OperationValidation


@dataclass(frozen=True, kw_only=True)
class Invocation:
    """Resolved operation identity used throughout retries and checkpoints."""

    project_id: ProjectId
    model_id: ModelId | None
    operation: str
    idempotency_key: str
    request_hash: ContentHash
    actor: str
    parent_audit_id: AuditId | None = None

    def __post_init__(self) -> None:
        """Require explicit attribution and a resolved operation and key."""
        OperationValidation.require_nonblank(value=self.actor, field="Actor")
        OperationValidation.require_nonblank(value=self.operation, field="Operation")
        OperationValidation.require_nonblank(value=self.idempotency_key, field="Idempotency key")

    @classmethod
    def resolve(  # noqa: PLR0913 - All resolved scope and attribution fields are explicit.
        cls,
        *,
        project_id: ProjectId,
        model_id: ModelId | None,
        operation: str,
        actor: str,
        key: str | None,
        intent: JsonValue,
        parent_audit_id: AuditId | None = None,
    ) -> Self:
        """Bind a scoped retry key to the actor, audit parent and canonical intent.

        Args:
            project_id: Project that owns the operation.
            model_id: Model scope, or None for a project-level operation.
            operation: Stable name of the operation within the scope.
            actor: Nonblank identity to record for the operation.
            key: Nonblank retry key. Pass None to generate a fresh key for this call.
            intent: Canonical input values that must match on replay.
            parent_audit_id: Optional audit parent included in the request hash.
        """
        return cls(
            project_id=project_id,
            model_id=model_id,
            operation=operation,
            idempotency_key=uuid4().hex if key is None else key,
            request_hash=Hashing.hash_json(
                value={
                    "actor": actor,
                    "intent": intent,
                    "parent_audit_id": parent_audit_id.value if parent_audit_id else None,
                }
            ),
            actor=actor,
            parent_audit_id=parent_audit_id,
        )
