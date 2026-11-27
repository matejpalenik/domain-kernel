from __future__ import annotations

from typing import final

from sqlalchemy import (
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.shared.infrastructure.persistence.sqlalchemy_base import SqlAlchemyBase


@final
class ProjectRow(SqlAlchemyBase):
    """Persist the project's stable identity and initial catalog metadata."""

    __tablename__ = "dk_project"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
