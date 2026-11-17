"""Append-only model definition and review snapshots over a shared SQLite transaction."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import TYPE_CHECKING, final, override

from sqlalchemy import (
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    delete,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel._shared.domain.definitions import Definition
from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.definition_errors import (
    DefinitionAlreadyExistsError,
    DefinitionNotFoundError,
)
from domain_kernel.review.application.ports import DefinitionRepository, ReviewRepository
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.review.domain.models import DecisionRecord, ReviewCase, ReviewReceipt
from domain_kernel.shared.contracts import Page
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.page_cursor import PageCursor

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.elements import ColumnElement

    from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
    from domain_kernel.review.domain.enums.case_kind import CaseKind
    from domain_kernel.review.domain.enums.case_status import CaseStatus
    from domain_kernel.review.domain.identifiers.decision_id import DecisionId
    from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
    from domain_kernel.shared.contracts import ModelScope


class _Scoped:
    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)


def _scope(*, row: type[_Scoped], scope: ModelScope) -> tuple[ColumnElement[bool], ...]:
    return row.project_id == scope.project_id.value, row.model_id == scope.model_id.value


@final
class _DefinitionIdentity(_Scoped, SQLiteBase):
    __tablename__ = "dk_definition"
    __table_args__: tuple[ForeignKeyConstraint | UniqueConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
        UniqueConstraint("project_id", "model_id", "name", name="dk_definition_model_name"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    current_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)


@final
class _DefinitionRevision(_Scoped, SQLiteBase):
    __tablename__ = "dk_definition_revision"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(
            ["project_id", "model_id", "identity"],
            ["dk_definition.project_id", "dk_definition.model_id", "dk_definition.id"],
        ),
    )

    identity: Mapped[str] = mapped_column(String, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)


@final
class _CaseHead(_Scoped, SQLiteBase):
    __tablename__ = "dk_review_case"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)


@final
class _CaseVersion(_Scoped, SQLiteBase):
    __tablename__ = "dk_review_case_version"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(
            ["project_id", "model_id", "identity"],
            ["dk_review_case.project_id", "dk_review_case.model_id", "dk_review_case.id"],
        ),
    )

    identity: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)


@final
class _CaseDiscovery(_Scoped, SQLiteBase):
    __tablename__ = "dk_review_case_discovery"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(
            ["project_id", "model_id", "case_id"],
            ["dk_review_case.project_id", "dk_review_case.model_id", "dk_review_case.id"],
        ),
        ForeignKeyConstraint(
            ["project_id", "model_id", "alignment_id"],
            ["dk_reconciliation.project_id", "dk_reconciliation.model_id", "dk_reconciliation.id"],
        ),
    )

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String)
    alignment_id: Mapped[str | None] = mapped_column(String)


@final
class _Decision(_Scoped, SQLiteBase):
    __tablename__ = "dk_decision"
    __table_args__: tuple[ForeignKeyConstraint | UniqueConstraint, ...] = (
        ForeignKeyConstraint(
            ["project_id", "model_id", "case_id"],
            ["dk_review_case.project_id", "dk_review_case.model_id", "dk_review_case.id"],
        ),
        UniqueConstraint("project_id", "model_id", "case_id", "version", name="dk_case_decision"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    receipt: Mapped[bytes] = mapped_column(LargeBinary)


def _page_key(*, scope: ModelScope, query: Sequence[str | None]) -> str:
    return hash_json(value=[scope.project_id.value, scope.model_id.value, *query]).value


def _continue(*, cursor: PageCursor | None, key: str, limit: int) -> str:
    if type(limit) is not int or limit < 1:
        raise ValueError("Page limit must be a positive integer")
    if cursor is None:
        return ""
    try:
        saved_key, offset = urlsafe_b64decode(cursor.value).decode("utf-8").split(",", maxsplit=1)
        if key == saved_key:
            return offset
    except ValueError:
        pass
    raise ValueError("Use a cursor returned by the same query")


def _page[T](
    *,
    rows: Sequence[tuple[str, bytes]],
    key: str,
    limit: int,
    restore: Callable[[bytes], T],
) -> Page[T]:
    selected = rows[:limit]
    continuation = None
    if len(rows) > limit:
        value = urlsafe_b64encode(f"{key},{selected[-1][0]}".encode()).decode("ascii")
        continuation = PageCursor(value=value)
    return Page(items=tuple(restore(value) for _, value in selected), next_cursor=continuation)


def _definition(payload: bytes, /) -> Definition:
    return read_record(content=payload, expected=Definition)


def _case(payload: bytes, /) -> ReviewCase:
    return read_record(content=payload, expected=ReviewCase)


def _decision(payload: bytes, /) -> DecisionRecord:
    return read_record(content=payload, expected=DecisionRecord)


@final
class SQLiteDefinitions(DefinitionRepository):
    """Reserve names and maintain the current pointer over immutable revisions."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's session."""
        self._session = session

    @override
    async def reserve(self, *, definition: Definition) -> None:
        created = await self._session.scalar(
            insert(_DefinitionIdentity)
            .values(
                project_id=definition.scope.project_id.value,
                model_id=definition.scope.model_id.value,
                id=definition.id.value,
                name=definition.name,
                current_revision=0,
                status=DefinitionStatus.PROPOSED.value,
            )
            .on_conflict_do_nothing(
                index_elements=(
                    _DefinitionIdentity.project_id,
                    _DefinitionIdentity.model_id,
                    _DefinitionIdentity.name,
                ),
            )
            .returning(_DefinitionIdentity.id),
        )
        if created is None:
            raise DefinitionAlreadyExistsError

    @override
    async def release(self, *, definition: Definition) -> None:
        _ = await self._session.execute(
            delete(_DefinitionIdentity).where(
                *_scope(row=_DefinitionIdentity, scope=definition.scope),
                _DefinitionIdentity.id == definition.id.value,
                _DefinitionIdentity.current_revision == 0,
            )
        )

    @override
    async def append(self, *, definition: Definition) -> None:
        updated = await self._session.scalar(
            update(_DefinitionIdentity)
            .where(
                *_scope(row=_DefinitionIdentity, scope=definition.scope),
                _DefinitionIdentity.id == definition.id.value,
                _DefinitionIdentity.name == definition.name,
                _DefinitionIdentity.current_revision == definition.revision - 1,
            )
            .values(
                current_revision=definition.revision,
                status=definition.status.value,
            )
            .returning(_DefinitionIdentity.id)
        )
        if updated is None:
            raise StaleStateError
        self._session.add(
            _DefinitionRevision(
                project_id=definition.scope.project_id.value,
                model_id=definition.scope.model_id.value,
                identity=definition.id.value,
                revision=definition.revision,
                content=record_bytes(value=definition),
            )
        )
        await self._session.flush()

    @override
    async def get(
        self,
        *,
        scope: ModelScope,
        name: str | None,
        definition_id: DefinitionId | None,
        revision: int | None,
    ) -> Definition:
        selector = (
            _DefinitionIdentity.name == name
            if definition_id is None
            else _DefinitionIdentity.id == definition_id.value
        )
        identity = await self._session.scalar(
            select(_DefinitionIdentity).where(
                *_scope(row=_DefinitionIdentity, scope=scope),
                selector,
            )
        )
        if identity is None:
            raise DefinitionNotFoundError
        content = await self._session.scalar(
            select(_DefinitionRevision.content).where(
                *_scope(row=_DefinitionRevision, scope=scope),
                _DefinitionRevision.identity == identity.id,
                _DefinitionRevision.revision
                == (identity.current_revision if revision is None else revision),
            )
        )
        if content is None:
            raise DefinitionNotFoundError
        return _definition(content)

    @override
    async def list(
        self,
        *,
        scope: ModelScope,
        status: DefinitionStatus | None,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Definition]:
        key = _page_key(scope=scope, query=["definitions", status.value if status else None])
        after = _continue(cursor=cursor, key=key, limit=limit)
        query = (
            self._current(scope=scope, status=status)
            .where(
                _DefinitionIdentity.name > after,
            )
            .order_by(_DefinitionIdentity.name)
            .limit(limit + 1)
        )
        rows = await self._session.execute(query)
        return _page(
            rows=tuple((name, content) for name, content in rows),
            key=key,
            limit=limit,
            restore=_definition,
        )

    @override
    async def active(self, *, scope: ModelScope) -> tuple[Definition, ...]:
        rows = await self._session.execute(
            self._current(scope=scope, status=DefinitionStatus.APPROVED)
        )
        return tuple(_definition(content) for _, content in rows)

    @staticmethod
    def _current(*, scope: ModelScope, status: DefinitionStatus | None) -> Select[str, bytes]:
        query = (
            select(_DefinitionIdentity.name, _DefinitionRevision.content)
            .join(
                _DefinitionRevision,
                (_DefinitionRevision.project_id == _DefinitionIdentity.project_id)
                & (_DefinitionRevision.model_id == _DefinitionIdentity.model_id)
                & (_DefinitionRevision.identity == _DefinitionIdentity.id)
                & (_DefinitionRevision.revision == _DefinitionIdentity.current_revision),
            )
            .where(*_scope(row=_DefinitionIdentity, scope=scope))
        )
        if status is not None:
            query = query.where(_DefinitionIdentity.status == status.value)
        return query

    @override
    async def history(
        self,
        *,
        scope: ModelScope,
        definition_id: DefinitionId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Definition]:
        key = _page_key(scope=scope, query=["definition-history", definition_id.value])
        after = int(_continue(cursor=cursor, key=key, limit=limit) or 0)
        result = await self._session.execute(
            select(_DefinitionRevision.revision, _DefinitionRevision.content)
            .where(
                *_scope(row=_DefinitionRevision, scope=scope),
                _DefinitionRevision.identity == definition_id.value,
                _DefinitionRevision.revision > after,
            )
            .order_by(_DefinitionRevision.revision)
            .limit(limit + 1)
        )
        return _page(
            rows=tuple((str(revision), content) for revision, content in result),
            key=key,
            limit=limit,
            restore=_definition,
        )


@final
class SQLiteReviews(ReviewRepository):
    """Store immutable review case and decision versions inside the owning transaction."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's session."""
        self._session = session

    @override
    async def add(self, *, case: ReviewCase) -> None:
        self._session.add(
            _CaseHead(
                project_id=case.scope.project_id.value,
                model_id=case.scope.model_id.value,
                id=case.id.value,
                version=case.version,
                kind=case.kind.value,
                status=case.status.value,
            )
        )
        await self._session.flush()
        if case.run_id is not None or case.reconciliation_id is not None:
            self._session.add(
                _CaseDiscovery(
                    project_id=case.scope.project_id.value,
                    model_id=case.scope.model_id.value,
                    case_id=case.id.value,
                    run_id=None if case.run_id is None else case.run_id.value,
                    alignment_id=None
                    if case.reconciliation_id is None
                    else case.reconciliation_id.value,
                )
            )
        await self._append(case=case)

    async def _append(self, *, case: ReviewCase) -> None:
        self._session.add(
            _CaseVersion(
                project_id=case.scope.project_id.value,
                model_id=case.scope.model_id.value,
                identity=case.id.value,
                version=case.version,
                content=record_bytes(value=case),
            )
        )
        await self._session.flush()

    @override
    async def save(self, *, case: ReviewCase, expected_version: int) -> None:
        updated = await self._session.scalar(
            update(_CaseHead)
            .where(
                *_scope(row=_CaseHead, scope=case.scope),
                _CaseHead.id == case.id.value,
                _CaseHead.version == expected_version,
            )
            .values(version=case.version, status=case.status.value)
            .returning(_CaseHead.id)
        )
        if updated is None:
            raise StaleStateError
        await self._append(case=case)

    @override
    async def get(
        self,
        *,
        scope: ModelScope,
        case_id: ReviewCaseId,
        version: int | None,
    ) -> ReviewCase:
        query = select(_CaseVersion.content).where(
            *_scope(row=_CaseVersion, scope=scope),
            _CaseVersion.identity == case_id.value,
        )
        if version is not None:
            query = query.where(_CaseVersion.version == version)
        content = await self._session.scalar(query.order_by(_CaseVersion.version.desc()).limit(1))
        if content is None:
            raise InvalidDecisionError(message="Open an existing review case from this model")
        return _case(content)

    @override
    async def list(
        self,
        *,
        scope: ModelScope,
        kind: CaseKind | None,
        status: CaseStatus | None,
        limit: int,
        cursor: PageCursor | None,
        run_id: DiscoveryRunId | None = None,
        reconciliation_id: AlignmentId | None = None,
    ) -> Page[ReviewCase]:
        key = _page_key(
            scope=scope,
            query=[
                "cases",
                kind.value if kind else None,
                status.value if status else None,
                run_id.value if run_id else None,
                reconciliation_id.value if reconciliation_id else None,
            ],
        )
        after = _continue(cursor=cursor, key=key, limit=limit)
        query = (
            select(_CaseHead.id, _CaseVersion.content)
            .join(
                _CaseVersion,
                (_CaseVersion.project_id == _CaseHead.project_id)
                & (_CaseVersion.model_id == _CaseHead.model_id)
                & (_CaseVersion.identity == _CaseHead.id)
                & (_CaseVersion.version == _CaseHead.version),
            )
            .where(*_scope(row=_CaseHead, scope=scope), _CaseHead.id > after)
        )
        if kind is not None:
            query = query.where(_CaseHead.kind == kind.value)
        if status is not None:
            query = query.where(_CaseHead.status == status.value)
        if run_id is not None or reconciliation_id is not None:
            query = query.join(
                _CaseDiscovery,
                (_CaseDiscovery.project_id == _CaseHead.project_id)
                & (_CaseDiscovery.model_id == _CaseHead.model_id)
                & (_CaseDiscovery.case_id == _CaseHead.id),
            )
        if run_id is not None:
            query = query.where(_CaseDiscovery.run_id == run_id.value)
        if reconciliation_id is not None:
            query = query.where(_CaseDiscovery.alignment_id == reconciliation_id.value)
        rows = await self._session.execute(query.order_by(_CaseHead.id).limit(limit + 1))
        return _page(
            rows=tuple((identity, content) for identity, content in rows),
            key=key,
            limit=limit,
            restore=_case,
        )

    @override
    async def record(self, *, decision: DecisionRecord, receipt: ReviewReceipt) -> None:
        self._session.add(
            _Decision(
                project_id=decision.scope.project_id.value,
                model_id=decision.scope.model_id.value,
                id=decision.id.value,
                case_id=decision.case_id.value,
                version=decision.case_version,
                content=record_bytes(value=decision),
                receipt=record_bytes(value=receipt),
            )
        )
        await self._session.flush()

    @override
    async def receipt(self, *, scope: ModelScope, decision_id: DecisionId) -> ReviewReceipt:
        content = await self._session.scalar(
            select(_Decision.receipt).where(
                *_scope(row=_Decision, scope=scope),
                _Decision.id == decision_id.value,
            )
        )
        if content is None:
            raise InvalidDecisionError(
                message="The committed decision is unavailable in this model"
            )
        return read_record(content=content, expected=ReviewReceipt)

    @override
    async def history(
        self,
        *,
        scope: ModelScope,
        case_id: ReviewCaseId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[DecisionRecord]:
        key = _page_key(scope=scope, query=["review-history", case_id.value])
        after = int(_continue(cursor=cursor, key=key, limit=limit) or 0)
        rows = await self._session.execute(
            select(_Decision.version, _Decision.content)
            .where(
                *_scope(row=_Decision, scope=scope),
                _Decision.case_id == case_id.value,
                _Decision.version > after,
            )
            .order_by(_Decision.version)
            .limit(limit + 1)
        )
        return _page(
            rows=tuple((str(version), content) for version, content in rows),
            key=key,
            limit=limit,
            restore=_decision,
        )
