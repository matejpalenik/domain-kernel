from __future__ import annotations

from typing import final

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.shared.infrastructure.persistence.sqlalchemy_base import SqlAlchemyBase


@final
class OperationRow(SqlAlchemyBase):
    """The durable intent, current lease and committed result of an idempotent operation."""

    __tablename__ = "dk_operation"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint(
            """(lease_token IS NULL AND lease_owner IS NULL AND expires_at IS NULL) OR
            (lease_token IS NOT NULL AND lease_owner IS NOT NULL AND expires_at IS NOT NULL)""",
            name="dk_operation_lease_complete",
        ),
        CheckConstraint(
            """(result_kind IS NULL AND result_id IS NULL AND result_version IS NULL) OR
            (result_kind IS NOT NULL AND result_id IS NOT NULL AND lease_token IS NULL)""",
            name="dk_operation_result_complete",
        ),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    # The empty key is reserved for project-scoped operations. ModelId rejects empty values.
    model_key: Mapped[str] = mapped_column(String, primary_key=True)
    operation: Mapped[str] = mapped_column(String, primary_key=True)
    request_key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    lease_token: Mapped[str | None] = mapped_column(String)
    lease_owner: Mapped[str | None] = mapped_column(String)
    expires_at: Mapped[str | None] = mapped_column(String)
    result_kind: Mapped[str | None] = mapped_column(String)
    result_id: Mapped[str | None] = mapped_column(String)
    result_version: Mapped[str | None] = mapped_column(String)
