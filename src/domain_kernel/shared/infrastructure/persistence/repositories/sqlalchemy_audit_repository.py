from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override

from sqlalchemy import func, select

from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.application.protocols.artifact_audit import ArtifactAudit
from domain_kernel.shared.application.protocols.audit_repository import AuditRepository
from domain_kernel.shared.application.results.page import Page
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.entities.audit_record import AuditRecord
from domain_kernel.shared.domain.enums.audit_action import AuditAction
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.domain.types.audit_resource_id import AUDIT_RESOURCE_TYPES
from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.identifiers.content_hash import ContentHash

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.shared.application.results.page_cursor import PageCursor
    from domain_kernel.shared.domain.types.audit_resource_id import AuditResourceId

from domain_kernel.shared.infrastructure.persistence.audit_window import AuditWindow
from domain_kernel.shared.infrastructure.persistence.rows.audit_row import AuditRow
from domain_kernel.shared.infrastructure.persistence.rows.effect_row import EffectRow

_RESOURCE_TYPES: dict[str, type[AuditResourceId]] = {
    identity.__name__: identity for identity in AUDIT_RESOURCE_TYPES
}


@final
class SqlAlchemyAuditRepository(AuditRepository, ArtifactAudit):
    """Record and page append-only audit events from the current operation."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's shared session."""
        self._session = session

    @override
    async def append(self, *, record: AuditRecord) -> None:
        """Persist the attributed event and its effects in the caller's transaction."""
        if record.parent_id is not None:
            parent = await self._session.scalar(
                select(AuditRow).where(AuditRow.id == record.parent_id.value),
            )
            if (
                parent is None
                or parent.project_id != record.project_id.value
                or (
                    parent.model_id is not None
                    and parent.model_id
                    != (record.model_id.value if record.model_id is not None else None)
                )
            ):
                raise ValueError("Audit parent must exist in the same scope or its project")

        row = AuditRow(
            id=record.id.value,
            project_id=record.project_id.value,
            model_id=record.model_id.value if record.model_id is not None else None,
            action=record.action.value,
            outcome=record.outcome.value,
            actor=record.actor,
            recorded_at=record.recorded_at.astimezone(UTC).isoformat(),
            reason=record.reason,
            parent_id=record.parent_id.value if record.parent_id is not None else None,
        )
        self._session.add(row)
        await self._session.flush()

        self._session.add_all(
            self._effects(event=row.number, group="before", effects=record.before)
        )
        self._session.add_all(self._effects(event=row.number, group="after", effects=record.after))
        if record.requested_artifact is not None:
            self._session.add_all(
                self._effects(
                    event=row.number,
                    group="intent",
                    effects=(record.requested_artifact,),
                )
            )

        await self._session.flush()

    @override
    async def get(self, *, audit_id: AuditId) -> AuditRecord | None:
        """Read one exact journal event with its immutable effects."""
        row = await self._session.scalar(select(AuditRow).where(AuditRow.id == audit_id.value))
        if row is None:
            return None

        effects = await self._session.scalars(
            select(EffectRow)
            .where(EffectRow.event == row.number)
            .order_by(EffectRow.group, EffectRow.position)
        )

        return self._materialize(row=row, effects=effects.all())

    @override
    async def list(
        self,
        *,
        project_id: ProjectId,
        model_id: ModelId | None,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[AuditRecord]:
        """Read one scoped page of committed history within its stable sequence window."""
        if type(limit) is not int or limit < 1:
            raise ValueError("Audit page limit must be a positive integer")

        scope = [AuditRow.project_id == project_id.value]
        if model_id is not None:
            scope.append(AuditRow.model_id == model_id.value)

        key = Hashing.hash_json(
            value=["audit", project_id.value, model_id.value if model_id else None]
        ).value

        if cursor is None:
            ceiling = await self._session.scalar(select(func.max(AuditRow.number)).where(*scope))
            if ceiling is None:
                return Page(items=())
            window = AuditWindow(last=0, ceiling=ceiling)
        else:
            window = AuditWindow.decode(cursor=cursor, key=key)

        rows = (
            await self._session.scalars(
                select(AuditRow)
                .where(
                    *scope,
                    AuditRow.number > window.last,
                    AuditRow.number <= window.ceiling,
                )
                .order_by(AuditRow.number)
                .limit(limit + 1),
            )
        ).all()

        selected = rows[:limit]
        groups: dict[int, list[EffectRow]] = defaultdict(list)
        if selected:
            effects = await self._session.scalars(
                select(EffectRow)
                .where(
                    EffectRow.event.in_(tuple(row.number for row in selected)),
                )
                .order_by(EffectRow.event, EffectRow.group, EffectRow.position),
            )

            for effect in effects:
                groups[effect.event].append(effect)

        next_cursor = (
            AuditWindow(last=selected[-1].number, ceiling=window.ceiling).encode(key=key)
            if len(rows) > limit
            else None
        )

        return Page(
            items=tuple(self._materialize(row=row, effects=groups[row.number]) for row in selected),
            next_cursor=next_cursor,
        )

    @staticmethod
    def _effects(
        *,
        event: int,
        group: str,
        effects: Sequence[AuditResource | Artifact],
    ) -> Iterable[EffectRow]:
        """Validate and encode ordered before and after effects for the event row."""
        for position, effect in enumerate(effects):
            if isinstance(effect, Artifact):
                yield EffectRow(
                    event=event,
                    group=group,
                    position=position,
                    kind="artifact-record",
                    identity=RecordCodec.encode(value=effect).decode("utf-8"),
                    content_hash=effect.content_hash.value,
                    store=effect.store,
                    provider_version=effect.provider_version,
                )
            else:
                yield EffectRow(
                    event=event,
                    group=group,
                    position=position,
                    kind=type(effect.resource_id).__name__,
                    identity=effect.resource_id.value,
                    revision=effect.revision,
                    content_hash=effect.content_hash.value,
                )

    @staticmethod
    def _load_effect(
        *, row: EffectRow, project_id: ProjectId, model_id: ModelId | None
    ) -> AuditResource | Artifact:
        """Restore an encoded effect of the declared durable kind."""
        content_hash = ContentHash(value=row.content_hash)

        if row.kind == "artifact-record":
            artifact = RecordCodec.decode(content=row.identity.encode("utf-8"), expected=Artifact)
            if (
                artifact.project_id != project_id
                or artifact.model_id != model_id
                or artifact.content_hash != content_hash
            ):
                raise ValueError("Stored audit artifact scope or digest disagrees")

            return artifact

        if row.kind == "artifact":
            if row.store is None:
                raise ValueError("Stored audit artifact lacks a destination")

            return Artifact(
                project_id=project_id,
                model_id=model_id,
                content_hash=content_hash,
                store=row.store,
                key=row.identity,
                provider_version=row.provider_version,
            )

        return AuditResource(
            resource_id=_RESOURCE_TYPES[row.kind](value=row.identity),
            revision=row.revision,
            content_hash=content_hash,
        )

    @staticmethod
    def _materialize(*, row: AuditRow, effects: Sequence[EffectRow]) -> AuditRecord:
        """Reconstruct the detached event and preserve its effect order."""
        project_id = ProjectId(value=row.project_id)
        model_id = ModelId(value=row.model_id) if row.model_id is not None else None

        groups: dict[str, list[AuditResource | Artifact]] = defaultdict(list)

        for effect in effects:
            groups[effect.group].append(
                SqlAlchemyAuditRepository._load_effect(
                    row=effect, project_id=project_id, model_id=model_id
                )
            )

        intent = groups.get("intent", [])
        requested = intent[0] if intent else None
        if requested is not None and (type(requested) is not Artifact or len(intent) != 1):
            raise ValueError("Stored audit write intent must have exactly one destination")

        return AuditRecord(
            id=AuditId(value=row.id),
            project_id=project_id,
            model_id=model_id,
            action=AuditAction(row.action),
            outcome=AuditOutcome(row.outcome),
            actor=row.actor,
            recorded_at=datetime.fromisoformat(row.recorded_at),
            reason=row.reason,
            parent_id=AuditId(value=row.parent_id) if row.parent_id is not None else None,
            requested_artifact=requested,
            before=groups["before"],
            after=groups["after"],
        )
