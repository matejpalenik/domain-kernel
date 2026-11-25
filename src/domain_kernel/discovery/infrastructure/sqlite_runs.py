"""Version and page exact discovery run checkpoints over one SQLite session."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import TYPE_CHECKING, final, override

from sqlalchemy import ForeignKeyConstraint, Integer, LargeBinary, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.discovery.application.run_ports import DiscoveryRuns
from domain_kernel.discovery.domain.models import DiscoveryRun
from domain_kernel.shared.contracts import Page
from domain_kernel.shared.domain.record_encoding import read_record, record_bytes
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.shared.validation import require_exact

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.elements import ColumnElement

    from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
    from domain_kernel.discovery.domain.models import DiscoveryResult
    from domain_kernel.shared.contracts import ModelScope


_MAX_PAGE_SIZE = 100


@final
class _DiscoveryRow(SQLiteBase):
    __tablename__ = "dk_discovery_run"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)


def _scope(*, scope: ModelScope) -> tuple[ColumnElement[bool], ...]:
    return (
        _DiscoveryRow.project_id == scope.project_id.value,
        _DiscoveryRow.model_id == scope.model_id.value,
    )


def _continuation(*, cursor: PageCursor | None, key: str) -> str:
    if cursor is None:
        return ""
    require_exact(value=cursor, expected=PageCursor, field="Discovery cursor")
    try:
        previous, after = urlsafe_b64decode(cursor.value).decode().split(",", maxsplit=1)
        if previous == key and after:
            return after
    except ValueError:
        pass
    raise ValueError("Use a cursor returned by this model's discovery query.")


@final
class SQLiteDiscoveryRuns(DiscoveryRuns):
    """Persist captured run state with an exact workspace boundary."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Use the session owned by the caller's operation."""
        self._session = session

    @override
    async def add(self, *, run: DiscoveryRun) -> None:
        state = run.snapshot
        self._session.add(
            _DiscoveryRow(
                project_id=state.scope.project_id.value,
                model_id=state.scope.model_id.value,
                id=state.id.value,
                version=state.version,
                content=record_bytes(value=run),
            )
        )
        await self._session.flush()

    @override
    async def get(self, *, scope: ModelScope, run_id: DiscoveryRunId) -> DiscoveryRun:
        row = await self._session.get(
            _DiscoveryRow, (scope.project_id.value, scope.model_id.value, run_id.value)
        )
        if row is None:
            raise StaleStateError(message="Open a discovery run from this model.")
        return read_record(content=row.content, expected=DiscoveryRun)

    @override
    async def save(self, *, run: DiscoveryRun, expected_version: int) -> None:
        state = run.snapshot
        if state.version != expected_version + 1:
            raise StaleStateError(message="Advance the current discovery checkpoint once.")
        updated = await self._session.scalar(
            update(_DiscoveryRow)
            .where(
                *_scope(scope=state.scope),
                _DiscoveryRow.id == state.id.value,
                _DiscoveryRow.version == expected_version,
            )
            .values(version=state.version, content=record_bytes(value=run))
            .returning(_DiscoveryRow.id)
        )
        if updated is None:
            raise StaleStateError(message="Reload the current discovery checkpoint.")

    @override
    async def list(
        self,
        *,
        scope: ModelScope,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[DiscoveryResult]:
        require_exact(value=limit, expected=int, field="Discovery page limit")
        if not 1 <= limit <= _MAX_PAGE_SIZE:
            raise ValueError("Use a discovery page size between 1 and 100.")
        key = hash_json(value=("discovery", scope.project_id.value, scope.model_id.value)).value
        after = _continuation(cursor=cursor, key=key)
        rows = tuple(
            await self._session.execute(
                select(_DiscoveryRow.id, _DiscoveryRow.content)
                .where(*_scope(scope=scope), _DiscoveryRow.id > after)
                .order_by(_DiscoveryRow.id)
                .limit(limit + 1)
            )
        )
        selected = rows[:limit]
        return Page(
            items=tuple(
                read_record(content=payload, expected=DiscoveryRun).snapshot
                for _, payload in selected
            ),
            next_cursor=None
            if len(rows) <= limit
            else PageCursor(value=urlsafe_b64encode(f"{key},{selected[-1][0]}".encode()).decode()),
        )
