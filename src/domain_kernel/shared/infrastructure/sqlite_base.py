"""Declarative registry owned by the built-in SQLite adapter."""

from sqlalchemy.orm import DeclarativeBase


class SQLiteBase(DeclarativeBase):
    """Collect the ORM schema managed by SQLite setup."""
