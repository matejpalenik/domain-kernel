"""Append audit events and materialize bounded historical snapshots from SQLite."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, Integer, String, func, select
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.application.persistence import AuditRepository
from domain_kernel.shared.contracts import Page
from domain_kernel.shared.domain.codecs.record_encoding import read_record, record_bytes
from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.entities.audit_record import AuditRecord
from domain_kernel.shared.domain.enums.audit_action import AuditAction
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.domain.types.audit_resource_id import AUDIT_RESOURCE_TYPES
from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.shared.infrastructure.sqlite_base import SQLiteBase

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.shared.domain.types.audit_resource_id import AuditResourceId

_RESOURCE_TYPES: dict[str, type[AuditResourceId]] = {
    identity.__name__: identity for identity in AUDIT_RESOURCE_TYPES
}


@final
class _AuditRow(SQLiteBase):
    __tablename__ = "dk_audit"
    __table_args__: tuple[ForeignKeyConstraint | Index, ...] = (
        ForeignKeyConstraint(
            ["project_id", "model_id"],
            ["dk_model.project_id", "dk_model.id"],
        ),
        Index("dk_audit_project_order", "project_id", "number"),
        Index("dk_audit_model_order", "project_id", "model_id", "number"),
    )

    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    id: Mapped[str] = mapped_column(String, unique=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("dk_project.id"))
    model_id: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    recorded_at: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("dk_audit.id"))


@final
class _EffectRow(SQLiteBase):
    __tablename__ = "dk_audit_effect"

    event: Mapped[int] = mapped_column(ForeignKey("dk_audit.number"), primary_key=True)
    group: Mapped[str] = mapped_column(String, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    identity: Mapped[str] = mapped_column(String)
    revision: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String)
    store: Mapped[str | None] = mapped_column(String)
    provider_version: Mapped[str | None] = mapped_column(String)


def _effects(
    *,
    event: int,
    group: str,
    effects: Sequence[AuditResource | Artifact],
) -> Iterable[_EffectRow]:
    for position, effect in enumerate(effects):
        if isinstance(effect, Artifact):
            yield _EffectRow(
                event=event,
                group=group,
                position=position,
                kind="artifact-record",
                identity=record_bytes(value=effect).decode("utf-8"),
                content_hash=effect.content_hash.value,
                store=effect.store,
                provider_version=effect.provider_version,
            )
        else:
            yield _EffectRow(
                event=event,
                group=group,
                position=position,
                kind=type(effect.resource_id).__name__,
                identity=effect.resource_id.value,
                revision=effect.revision,
                content_hash=effect.content_hash.value,
            )


def _load_effect(
    *, row: _EffectRow, project_id: ProjectId, model_id: ModelId | None
) -> AuditResource | Artifact:
    content_hash = ContentHash(value=row.content_hash)
    if row.kind == "artifact-record":
        artifact = read_record(content=row.identity.encode("utf-8"), expected=Artifact)
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


def _materialize(*, row: _AuditRow, effects: Sequence[_EffectRow]) -> AuditRecord:
    project_id = ProjectId(value=row.project_id)
    model_id = ModelId(value=row.model_id) if row.model_id is not None else None
    groups: dict[str, list[AuditResource | Artifact]] = defaultdict(list)
    for effect in effects:
        groups[effect.group].append(
            _load_effect(row=effect, project_id=project_id, model_id=model_id)
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


@dataclass(frozen=True, kw_only=True)
class _Window:
    last: int
    ceiling: int

    @classmethod
    def decode(cls, *, cursor: PageCursor, key: str) -> _Window:
        try:
            parts = urlsafe_b64decode(cursor.value).decode("ascii").split(",")
            query, last, ceiling = parts
            if query == key and 0 < int(last) < int(ceiling):
                return cls(last=int(last), ceiling=int(ceiling))
        except ValueError:
            pass
        raise ValueError("Use a valid cursor from the same audit history query")

    def encode(self, *, key: str) -> PageCursor:
        return PageCursor(
            value=urlsafe_b64encode(f"{key},{self.last},{self.ceiling}".encode("ascii")).decode(
                "ascii"
            ),
        )


@final
class SQLiteAuditRepository(AuditRepository):
    """Record and page append-only audit events from the current operation."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's shared session."""
        self._session = session

    @override
    async def append(self, *, record: AuditRecord) -> None:
        if record.parent_id is not None:
            parent = await self._session.scalar(
                select(_AuditRow).where(_AuditRow.id == record.parent_id.value),
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
        row = _AuditRow(
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
        self._session.add_all(_effects(event=row.number, group="before", effects=record.before))
        self._session.add_all(_effects(event=row.number, group="after", effects=record.after))
        if record.requested_artifact is not None:
            self._session.add_all(
                _effects(
                    event=row.number,
                    group="intent",
                    effects=(record.requested_artifact,),
                )
            )
        await self._session.flush()

    async def get(self, *, audit_id: AuditId) -> AuditRecord | None:
        """Read one exact journal event with its immutable effects."""
        row = await self._session.scalar(select(_AuditRow).where(_AuditRow.id == audit_id.value))
        if row is None:
            return None
        effects = await self._session.scalars(
            select(_EffectRow)
            .where(_EffectRow.event == row.number)
            .order_by(_EffectRow.group, _EffectRow.position)
        )
        return _materialize(row=row, effects=effects.all())

    @override
    async def list(
        self,
        *,
        project_id: ProjectId,
        model_id: ModelId | None,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[AuditRecord]:
        if type(limit) is not int or limit < 1:
            raise ValueError("Audit page limit must be a positive integer")
        scope = [_AuditRow.project_id == project_id.value]
        if model_id is not None:
            scope.append(_AuditRow.model_id == model_id.value)
        key = hash_json(
            value=["audit", project_id.value, model_id.value if model_id else None]
        ).value
        if cursor is None:
            ceiling = await self._session.scalar(select(func.max(_AuditRow.number)).where(*scope))
            if ceiling is None:
                return Page(items=())
            window = _Window(last=0, ceiling=ceiling)
        else:
            window = _Window.decode(cursor=cursor, key=key)
        rows = (
            await self._session.scalars(
                select(_AuditRow)
                .where(
                    *scope,
                    _AuditRow.number > window.last,
                    _AuditRow.number <= window.ceiling,
                )
                .order_by(_AuditRow.number)
                .limit(limit + 1),
            )
        ).all()
        selected = rows[:limit]
        groups: dict[int, list[_EffectRow]] = defaultdict(list)
        if selected:
            effects = await self._session.scalars(
                select(_EffectRow)
                .where(
                    _EffectRow.event.in_(tuple(row.number for row in selected)),
                )
                .order_by(_EffectRow.event, _EffectRow.group, _EffectRow.position),
            )
            for effect in effects:
                groups[effect.event].append(effect)
        next_cursor = (
            _Window(last=selected[-1].number, ceiling=window.ceiling).encode(key=key)
            if len(rows) > limit
            else None
        )
        return Page(
            items=tuple(_materialize(row=row, effects=groups[row.number]) for row in selected),
            next_cursor=next_cursor,
        )
