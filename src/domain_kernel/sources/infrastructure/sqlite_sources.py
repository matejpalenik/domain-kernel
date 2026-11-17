"""Project-scoped source metadata, immutable revisions and completed outcomes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.shared.contracts import Page
from domain_kernel.shared.errors import ScopeMismatchError, SourceNotFoundError, StaleStateError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.sources.application.ports import SourceRepository
from domain_kernel.sources.domain.errors.source_already_exists_error import SourceAlreadyExistsError
from domain_kernel.sources.domain.models import (
    IngestedSource,
    OriginalWriteIntent,
    Source,
    SourceProfile,
    SourceRevision,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.sources.domain.identifiers.source_id import SourceId
    from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
    from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId


@final
class _SourceRow(SQLiteBase):
    __tablename__ = "dk_source"
    __table_args__: tuple[UniqueConstraint, ...] = (UniqueConstraint("project_id", "name"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("dk_project.id"), primary_key=True)
    identity: Mapped[str] = mapped_column(String, primary_key=True, unique=True)
    name: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)


@final
class _RevisionRow(SQLiteBase):
    __tablename__ = "dk_source_revision"
    __table_args__: tuple[ForeignKeyConstraint | UniqueConstraint, ...] = (
        ForeignKeyConstraint(
            ["project_id", "source_id"],
            ["dk_source.project_id", "dk_source.identity"],
        ),
        UniqueConstraint("project_id", "source_id", "revision_id"),
    )

    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    revision_id: Mapped[str] = mapped_column(String)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class _OwnedPayload:
    project_id: Mapped[str] = mapped_column(ForeignKey("dk_project.id"), primary_key=True)
    identity: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


@final
class _IngestionRow(_OwnedPayload, SQLiteBase):
    __tablename__ = "dk_source_ingestion"

    source_id: Mapped[str] = mapped_column(String)
    revision_id: Mapped[str] = mapped_column(String)
    recorded_at: Mapped[str] = mapped_column(String)
    profile_data: Mapped[bytes | None] = mapped_column(LargeBinary)


@final
class _ManifestRow(_OwnedPayload, SQLiteBase):
    __tablename__ = "dk_source_manifest"


@final
class _ManifestEntryRow(SQLiteBase):
    __tablename__ = "dk_source_manifest_entry"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(
            ["project_id", "manifest_id"],
            ["dk_source_manifest.project_id", "dk_source_manifest.identity"],
        ),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    manifest_id: Mapped[str] = mapped_column(String)


@final
class _CopyIntentRow(_OwnedPayload, SQLiteBase):
    __tablename__ = "dk_source_copy_intent"


def _offset(*, cursor: PageCursor | None, binding: str, limit: int) -> str:
    if type(limit) is not int or limit < 1:
        raise ValueError("Use a positive page limit")
    if cursor is None:
        return ""
    key, delimiter, offset = cursor.value.rpartition(":")
    if not delimiter or key != binding or not offset:
        raise ValueError("Use a continuation from this source query")
    return offset


def _page[T](
    *,
    rows: Sequence[tuple[str | int, bytes]],
    binding: str,
    limit: int,
    kind: type[T],
) -> Page[T]:
    selected = rows[:limit]
    continuation = PageCursor(value=f"{binding}:{selected[-1][0]}") if len(rows) > limit else None
    return Page(
        items=tuple(read_record(content=data, expected=kind) for _, data in selected),
        next_cursor=continuation,
    )


@final
class SQLiteSources(SourceRepository):
    """Store scoped immutable acquisition state in the caller's transaction."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the existing operation session."""
        self._session = session

    @override
    async def get(self, *, project_id: ProjectId, source_id: SourceId) -> Source:
        match = await self._session.execute(
            select(_SourceRow.project_id, _SourceRow.data).where(
                _SourceRow.identity == source_id.value
            )
        )
        row = match.first()
        if row is None:
            raise SourceNotFoundError
        owning_project, data = row
        if owning_project != project_id.value:
            raise ScopeMismatchError
        return read_record(content=data, expected=Source)

    @override
    async def find_by_name(self, *, project_id: ProjectId, name: str) -> Source | None:
        data = await self._session.scalar(
            select(_SourceRow.data).where(
                _SourceRow.project_id == project_id.value, _SourceRow.name == name
            ),
        )
        return read_record(content=data, expected=Source) if data is not None else None

    @override
    async def save(self, *, source: Source, expected_version: int | None) -> None:
        data = record_bytes(value=source)
        if expected_version is None:
            created = await self._session.scalar(
                insert(_SourceRow)
                .values(
                    project_id=source.project_id.value,
                    identity=source.id.value,
                    name=source.name,
                    version=source.version,
                    data=data,
                )
                .on_conflict_do_nothing(index_elements=(_SourceRow.project_id, _SourceRow.name))
                .returning(_SourceRow.identity),
            )
            if created is None:
                raise SourceAlreadyExistsError
        else:
            updated = await self._session.scalar(
                update(_SourceRow)
                .where(
                    _SourceRow.project_id == source.project_id.value,
                    _SourceRow.identity == source.id.value,
                    _SourceRow.version == expected_version,
                )
                .values(version=source.version, data=data)
                .returning(_SourceRow.identity),
            )
            if updated is None:
                raise StaleStateError(message="Reload and inspect the current source revision")

    @override
    async def list(
        self,
        *,
        project_id: ProjectId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Source]:
        binding = hash_json(value=("sources", project_id.value)).value
        offset = _offset(cursor=cursor, binding=binding, limit=limit)
        result = await self._session.execute(
            select(_SourceRow.name, _SourceRow.data)
            .where(_SourceRow.project_id == project_id.value, _SourceRow.name > offset)
            .order_by(_SourceRow.name)
            .limit(limit + 1),
        )
        return _page(
            rows=tuple((offset, data) for offset, data in result),
            binding=binding,
            limit=limit,
            kind=Source,
        )

    @override
    async def revision(
        self,
        *,
        project_id: ProjectId,
        source_id: SourceId,
        revision_id: SourceRevisionId,
    ) -> SourceRevision | None:
        data = await self._session.scalar(
            select(_RevisionRow.data).where(
                _RevisionRow.project_id == project_id.value,
                _RevisionRow.source_id == source_id.value,
                _RevisionRow.revision_id == revision_id.value,
            ),
        )
        return read_record(content=data, expected=SourceRevision) if data is not None else None

    @override
    async def add_revision(self, *, revision: SourceRevision) -> None:
        self._session.add(
            _RevisionRow(
                project_id=revision.project_id.value,
                source_id=revision.source_id.value,
                revision_id=revision.revision_id.value,
                data=record_bytes(value=revision),
            ),
        )
        await self._session.flush()

    @override
    async def list_revisions(
        self,
        *,
        project_id: ProjectId,
        source_id: SourceId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[SourceRevision]:
        binding = hash_json(value=("source-revisions", project_id.value, source_id.value)).value
        offset = int(_offset(cursor=cursor, binding=binding, limit=limit) or "0")
        result = await self._session.execute(
            select(_RevisionRow.position, _RevisionRow.data)
            .where(
                _RevisionRow.project_id == project_id.value,
                _RevisionRow.source_id == source_id.value,
                _RevisionRow.position > offset,
            )
            .order_by(_RevisionRow.position)
            .limit(limit + 1),
        )
        return _page(
            rows=tuple((offset, data) for offset, data in result),
            binding=binding,
            limit=limit,
            kind=SourceRevision,
        )

    @override
    async def add_result(
        self,
        *,
        project_id: ProjectId,
        key: str,
        result: IngestedSource,
        profile: SourceProfile | None,
    ) -> None:
        self._session.add(
            _IngestionRow(
                project_id=project_id.value,
                identity=key,
                data=record_bytes(value=result),
                source_id=result.source_id.value,
                revision_id=result.revision_id.value,
                recorded_at=datetime.now(tz=UTC).isoformat(),
                profile_data=None if profile is None else record_bytes(value=profile),
            ),
        )
        await self._session.flush()

    @override
    async def profile(self, *, revision: SourceRevision) -> SourceProfile | None:
        content = await self._session.scalar(
            select(_IngestionRow.profile_data)
            .where(
                _IngestionRow.project_id == revision.project_id.value,
                _IngestionRow.source_id == revision.source_id.value,
                _IngestionRow.revision_id == revision.revision_id.value,
                _IngestionRow.profile_data.is_not(None),
            )
            .order_by(_IngestionRow.recorded_at.desc(), _IngestionRow.identity)
            .limit(1)
        )
        return read_record(content=content, expected=SourceProfile) if content is not None else None

    @override
    async def result(self, *, project_id: ProjectId, key: str) -> IngestedSource:
        data = await self._payload(row=_IngestionRow, project_id=project_id, key=key)
        return read_record(content=data, expected=IngestedSource)

    @override
    async def reserve_copy(
        self,
        *,
        project_id: ProjectId,
        key: str,
        intent: OriginalWriteIntent,
    ) -> None:
        self._session.add(
            _CopyIntentRow(
                project_id=project_id.value,
                identity=key,
                data=record_bytes(value=intent),
            ),
        )
        await self._session.flush()

    @override
    async def copy_intent(self, *, project_id: ProjectId, key: str) -> OriginalWriteIntent | None:
        content = await self._session.scalar(
            select(_CopyIntentRow.data).where(
                _CopyIntentRow.project_id == project_id.value,
                _CopyIntentRow.identity == key,
            ),
        )
        return read_record(content=content, expected=OriginalWriteIntent) if content else None

    @override
    async def add_manifest(
        self,
        *,
        project_id: ProjectId,
        identifier: SourceManifestId,
        content: bytes,
        entry_keys: Sequence[str],
    ) -> None:
        self._session.add(
            _ManifestRow(project_id=project_id.value, identity=identifier.value, data=content),
        )
        await self._session.flush()

        self._session.add_all(
            _ManifestEntryRow(project_id=project_id.value, key=key, manifest_id=identifier.value)
            for key in entry_keys
        )
        await self._session.flush()

    @override
    async def manifest(self, *, project_id: ProjectId, identifier: SourceManifestId) -> bytes:
        return await self._payload(row=_ManifestRow, project_id=project_id, key=identifier.value)

    @override
    async def manifest_for_item(self, *, project_id: ProjectId, key: str) -> bytes | None:
        return await self._session.scalar(
            select(_ManifestRow.data)
            .join(
                _ManifestEntryRow,
                (_ManifestEntryRow.project_id == _ManifestRow.project_id)
                & (_ManifestEntryRow.manifest_id == _ManifestRow.identity),
            )
            .where(_ManifestEntryRow.project_id == project_id.value, _ManifestEntryRow.key == key)
        )

    async def _payload(
        self,
        *,
        row: type[_OwnedPayload],
        project_id: ProjectId,
        key: str,
    ) -> bytes:
        data = await self._session.scalar(
            select(row.data).where(row.project_id == project_id.value, row.identity == key),
        )
        if data is None:
            raise StaleStateError(message="Reload the exact completed source operation")
        return data
