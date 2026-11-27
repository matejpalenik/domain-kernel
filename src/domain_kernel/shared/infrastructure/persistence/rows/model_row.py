from __future__ import annotations

from typing import final

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.shared.infrastructure.persistence.sqlalchemy_base import SqlAlchemyBase


@final
class ModelRow(SqlAlchemyBase):
    """Persist the scoped workspace and its current revision."""

    __tablename__ = "dk_model"
    __table_args__: tuple[UniqueConstraint | CheckConstraint, ...] = (
        UniqueConstraint("project_id", "name", name="dk_model_scoped_name"),
        CheckConstraint("revision >= 0", name="dk_model_nonnegative_revision"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("dk_project.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
