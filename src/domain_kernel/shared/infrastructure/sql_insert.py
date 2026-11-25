"""Use the database's conflict-safe insert for shared persistence repositories."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

if TYPE_CHECKING:
    from sqlalchemy.dialects.postgresql import Insert as PostgreSQLInsert
    from sqlalchemy.dialects.sqlite import Insert as SQLiteInsert
    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.shared.infrastructure.sqlite_base import SQLiteBase


def insert_once(*, session: AsyncSession, row: type[SQLiteBase]) -> PostgreSQLInsert | SQLiteInsert:
    """Select the matching conflict clause for the operation's bound dialect."""
    if session.get_bind().dialect.name == "postgresql":
        return postgres_insert(row)
    return sqlite_insert(row)
