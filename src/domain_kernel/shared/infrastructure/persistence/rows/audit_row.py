from __future__ import annotations

from typing import final

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.shared.infrastructure.persistence.sqlalchemy_base import SqlAlchemyBase


@final
class AuditRow(SqlAlchemyBase):
    """The scoped audit event and its durable sequence number."""

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
