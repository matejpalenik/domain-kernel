"""An attributed snapshot of one durable action and its actual outcome."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.enums.audit_action import AuditAction
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class AuditRecord:
    """An attributed snapshot of one durable action and its actual outcome."""

    id: AuditId
    project_id: ProjectId
    model_id: ModelId | None
    action: AuditAction
    outcome: AuditOutcome
    actor: str
    recorded_at: datetime
    before: Sequence[AuditResource | Artifact]
    after: Sequence[AuditResource | Artifact]
    reason: str | None = None
    parent_id: AuditId | None = None
    requested_artifact: Artifact | None = None

    def __post_init__(self) -> None:
        """Validate attribution and detach scoped effects from caller-owned inputs."""
        RuntimeTypeValidation.require_exact(value=self.id, expected=AuditId, field="Audit identity")
        RuntimeTypeValidation.require_exact(
            value=self.project_id, expected=ProjectId, field="Audit project"
        )
        if self.model_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.model_id, expected=ModelId, field="Audit model"
            )

        RuntimeTypeValidation.require_exact(
            value=self.action, expected=AuditAction, field="Audit action"
        )
        RuntimeTypeValidation.require_exact(
            value=self.outcome, expected=AuditOutcome, field="Audit outcome"
        )

        TextValidation.require_text(value=self.actor, field="Actor")
        if self.recorded_at.utcoffset() is None:
            raise ValueError("Audit time must include a time zone")
        if self.reason is not None:
            TextValidation.require_text(value=self.reason, field="Audit reason")

        if self.parent_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.parent_id, expected=AuditId, field="Parent audit identity"
            )
            if self.parent_id == self.id:
                raise ValueError("An audit event cannot be its own parent")

        object.__setattr__(self, "before", self._effects(items=self.before))
        object.__setattr__(self, "after", self._effects(items=self.after))

        if self.requested_artifact is not None:
            RuntimeTypeValidation.require_exact(
                value=self.requested_artifact, expected=Artifact, field="Requested artifact"
            )
            self._check_scope(effect=self.requested_artifact)

        if self.outcome in (AuditOutcome.STARTED, AuditOutcome.FAILED) and any(
            type(effect) is Artifact for effect in self.after
        ):
            raise ValueError("An unfinished write cannot record a verified artifact")

    def _effects(
        self,
        *,
        items: Sequence[AuditResource | Artifact],
    ) -> tuple[AuditResource | Artifact, ...]:
        """Freeze the event effects and require supported resource snapshots."""
        if not SequenceValidation.is_non_string_sequence(value=items):
            raise TypeError("Audit effects must be a sequence")
        effects = tuple(items)

        for effect in effects:
            if type(effect) not in (AuditResource, Artifact):
                raise TypeError("Audit effects must be typed resources or artifacts")
            self._check_scope(effect=effect)

        return effects

    def _check_scope(self, *, effect: AuditResource | Artifact) -> None:
        """Require every scoped effect to belong to the event's project and model."""
        if isinstance(effect, Artifact):
            if effect.project_id != self.project_id or effect.model_id != self.model_id:
                raise ValueError("Artifact does not belong to this audit scope")
        elif (type(effect.resource_id) is ProjectId and effect.resource_id != self.project_id) or (
            type(effect.resource_id) is ModelId and effect.resource_id != self.model_id
        ):
            raise ValueError("Resource does not belong to this audit scope")
