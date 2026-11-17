"""Persist scoped publication and release records in SQLite."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import TYPE_CHECKING, final, override

from sqlalchemy import ForeignKeyConstraint, Integer, LargeBinary, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel._shared.infrastructure.sql_insert import insert_once
from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.bundles import DomainModelBundle
from domain_kernel.modeling.application.publication_ports import PublicationRepository
from domain_kernel.modeling.domain.publications import Publication
from domain_kernel.shared.contracts import Page
from domain_kernel.shared.errors import PublicationNotFoundError, VersionExistsError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.page_cursor import PageCursor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.sql import Select
    from sqlalchemy.sql.elements import ColumnElement

    from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
    from domain_kernel.shared.contracts import ModelScope


@final
class _PublicationRow(SQLiteBase):
    __tablename__ = "dk_publication"
    __table_args__: tuple[UniqueConstraint | ForeignKeyConstraint, ...] = (
        UniqueConstraint("project_id", "model_id", "id", name="dk_unique_preparation"),
        ForeignKeyConstraint(
            ["project_id", "model_id", "candidate_id"],
            ["dk_candidate.project_id", "dk_candidate.model_id", "dk_candidate.id"],
        ),
    )

    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String)
    model_id: Mapped[str] = mapped_column(String)
    id: Mapped[str] = mapped_column(String)
    candidate_id: Mapped[str] = mapped_column(String)
    data: Mapped[bytes] = mapped_column(LargeBinary)


@final
class _BundleRow(SQLiteBase):
    __tablename__ = "dk_bundle"
    __table_args__: tuple[UniqueConstraint | ForeignKeyConstraint, ...] = (
        UniqueConstraint("project_id", "model_id", "version", name="dk_unique_model_version"),
        ForeignKeyConstraint(
            ["project_id", "model_id", "publication_id"],
            ["dk_publication.project_id", "dk_publication.model_id", "dk_publication.id"],
        ),
    )

    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String)
    model_id: Mapped[str] = mapped_column(String)
    id: Mapped[str] = mapped_column(String, unique=True)
    version: Mapped[str] = mapped_column(String)
    publication_id: Mapped[str] = mapped_column(String)
    data: Mapped[bytes] = mapped_column(LargeBinary)


def _bundle_scope(*, scope: ModelScope) -> tuple[ColumnElement[bool], ...]:
    return (
        _BundleRow.project_id == scope.project_id.value,
        _BundleRow.model_id == scope.model_id.value,
    )


def _offset(*, cursor: PageCursor | None, key: str) -> int:
    if cursor is None:
        return 0
    try:
        query, position = urlsafe_b64decode(cursor.value).decode("ascii").split(",")
        if query == key and int(position) > 0:
            return int(position)
    except ValueError:
        pass
    raise ValueError("Use a cursor returned by this version query")


def _page[T](
    *,
    rows: tuple[tuple[int, bytes], ...],
    limit: int,
    key: str,
    record: type[T],
) -> Page[T]:
    selected = rows[:limit]
    continuation = None
    if len(rows) > limit:
        value = urlsafe_b64encode(f"{key},{selected[-1][0]}".encode()).decode("ascii")
        continuation = PageCursor(value=value)
    return Page(
        items=tuple(
            read_record(content=data, expected=record, root_type=record) for _, data in selected
        ),
        next_cursor=continuation,
    )


@final
class SQLitePublications(PublicationRepository):
    """Retain preparations and versions in the caller's transaction."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the session shared with audit and idempotency."""
        self._session = session

    @override
    async def add_preparation(self, *, publication: Publication) -> None:
        self._session.add(
            _PublicationRow(
                project_id=publication.scope.project_id.value,
                model_id=publication.scope.model_id.value,
                id=publication.id.value,
                candidate_id=publication.candidate.id.value,
                data=record_bytes(value=publication),
            )
        )
        await self._session.flush()

    @override
    async def preparation(self, *, scope: ModelScope, publication_id: PublicationId) -> Publication:
        data = await self._session.scalar(
            select(_PublicationRow.data).where(
                _PublicationRow.project_id == scope.project_id.value,
                _PublicationRow.model_id == scope.model_id.value,
                _PublicationRow.id == publication_id.value,
            )
        )
        if data is None:
            raise PublicationNotFoundError
        return read_record(content=data, expected=Publication)

    @override
    async def list_preparations(
        self,
        *,
        scope: ModelScope,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Publication]:
        key = hash_json(value=["preparations", scope.project_id.value, scope.model_id.value]).value
        query = select(_PublicationRow.position, _PublicationRow.data).where(
            _PublicationRow.project_id == scope.project_id.value,
            _PublicationRow.model_id == scope.model_id.value,
        )
        return await self._list(
            query=query,
            position=_PublicationRow.position,
            limit=limit,
            cursor=cursor,
            key=key,
            record=Publication,
        )

    @override
    async def add_bundle(self, *, bundle: DomainModelBundle) -> None:
        position = await self._session.scalar(
            insert_once(session=self._session, row=_BundleRow)
            .values(
                project_id=bundle.scope.project_id.value,
                model_id=bundle.scope.model_id.value,
                id=bundle.id.value,
                version=bundle.version,
                publication_id=bundle.publication.id.value,
                data=record_bytes(value=bundle, root_type=DomainModelBundle),
            )
            .on_conflict_do_nothing(
                index_elements=(_BundleRow.project_id, _BundleRow.model_id, _BundleRow.version),
            )
            .returning(_BundleRow.position),
        )
        if position is None:
            raise VersionExistsError

    @override
    async def bundle(self, *, scope: ModelScope, version: str) -> DomainModelBundle:
        data = await self._session.scalar(
            select(_BundleRow.data).where(
                *_bundle_scope(scope=scope),
                _BundleRow.version == version,
            )
        )
        if data is None:
            raise PublicationNotFoundError
        return read_record(content=data, expected=DomainModelBundle, root_type=DomainModelBundle)

    @override
    async def latest(self, *, scope: ModelScope) -> DomainModelBundle | None:
        data = await self._session.scalar(
            select(_BundleRow.data)
            .where(
                *_bundle_scope(scope=scope),
            )
            .order_by(_BundleRow.position.desc())
            .limit(1)
        )
        return (
            None
            if data is None
            else read_record(content=data, expected=DomainModelBundle, root_type=DomainModelBundle)
        )

    @override
    async def list_versions(
        self,
        *,
        scope: ModelScope,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[DomainModelBundle]:
        key = hash_json(value=["versions", scope.project_id.value, scope.model_id.value]).value
        query = select(_BundleRow.position, _BundleRow.data).where(*_bundle_scope(scope=scope))
        return await self._list(
            query=query,
            position=_BundleRow.position,
            limit=limit,
            cursor=cursor,
            key=key,
            record=DomainModelBundle,
        )

    async def _list[T](  # noqa: PLR0913 - Both tables share the same scoped pagination contract.
        self,
        *,
        query: Select[int, bytes],
        position: InstrumentedAttribute[int],
        limit: int,
        cursor: PageCursor | None,
        key: str,
        record: type[T],
    ) -> Page[T]:
        if type(limit) is not int or limit < 1:
            raise ValueError("Page limit must be a positive integer")
        start = _offset(cursor=cursor, key=key)
        result = await self._session.execute(
            query.where(position > start).order_by(position).limit(limit + 1),
        )
        return _page(
            rows=tuple((index, data) for index, data in result),
            limit=limit,
            key=key,
            record=record,
        )
