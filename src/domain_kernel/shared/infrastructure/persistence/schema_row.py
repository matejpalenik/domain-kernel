from __future__ import annotations

from typing import final

from sqlalchemy import (
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.shared.infrastructure.persistence.sqlalchemy_base import SqlAlchemyBase


@final
class SchemaRow(SqlAlchemyBase):
    """The version of the initialized workspace schema."""

    __tablename__ = "dk_schema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
