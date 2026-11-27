from __future__ import annotations

from typing import final

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel.shared.infrastructure.persistence.sqlalchemy_base import SqlAlchemyBase


@final
class EffectRow(SqlAlchemyBase):
    """One ordered before or after effect belonging to an audit event."""

    __tablename__ = "dk_audit_effect"

    event: Mapped[int] = mapped_column(ForeignKey("dk_audit.number"), primary_key=True)
    group: Mapped[str] = mapped_column(String, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    identity: Mapped[str] = mapped_column(String)
    revision: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String)
    store: Mapped[str | None] = mapped_column(String)
    provider_version: Mapped[str | None] = mapped_column(String)
