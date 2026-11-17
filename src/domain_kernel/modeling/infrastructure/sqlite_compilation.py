"""Persist candidate and validation snapshots in the active SQLite transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from sqlalchemy import ForeignKeyConstraint, LargeBinary, String, select
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.modeling.application.compilation_ports import (
    CompilationRepository,
    CompiledSnapshot,
)
from domain_kernel.modeling.domain.snapshots import Candidate, ReviewSnapshot
from domain_kernel.shared.errors import StaleStateError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
    from domain_kernel.modeling.domain.snapshots import ValidationReport
    from domain_kernel.shared.contracts import ModelScope


@final
class _CandidateRow(SQLiteBase):
    __tablename__ = "dk_candidate"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate: Mapped[bytes] = mapped_column(LargeBinary)
    review: Mapped[bytes] = mapped_column(LargeBinary)


@final
class _ValidationRow(SQLiteBase):
    __tablename__ = "dk_validation_report"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(
            ["project_id", "model_id", "candidate_id"],
            ["dk_candidate.project_id", "dk_candidate.model_id", "dk_candidate.id"],
        ),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String)
    report: Mapped[bytes] = mapped_column(LargeBinary)


@final
class SQLiteCompilation(CompilationRepository):
    """Retain immutable candidates and reports scoped to an exact model."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation's session."""
        self._session = session

    @override
    async def add_candidate(self, *, snapshot: CompiledSnapshot) -> None:
        candidate = snapshot.candidate
        self._session.add(
            _CandidateRow(
                project_id=candidate.scope.project_id.value,
                model_id=candidate.scope.model_id.value,
                id=candidate.id.value,
                candidate=record_bytes(value=candidate),
                review=(
                    record_bytes(value=snapshot.review)
                    if snapshot.reference_pack is None
                    else record_bytes(value=snapshot, root_type=CompiledSnapshot)
                ),
            )
        )
        await self._session.flush()

    @override
    async def get_candidate(
        self, *, scope: ModelScope, candidate_id: CandidateId
    ) -> CompiledSnapshot:
        row = await self._session.scalar(
            select(_CandidateRow).where(
                _CandidateRow.project_id == scope.project_id.value,
                _CandidateRow.model_id == scope.model_id.value,
                _CandidateRow.id == candidate_id.value,
            )
        )
        if row is None:
            raise StaleStateError(message="Load a candidate saved in this exact model")
        candidate = read_record(content=row.candidate, expected=Candidate)
        if candidate.reference_pack is None:
            return CompiledSnapshot(
                candidate=candidate,
                review=read_record(content=row.review, expected=ReviewSnapshot),
            )
        snapshot = read_record(
            content=row.review, expected=CompiledSnapshot, root_type=CompiledSnapshot
        )
        if (
            snapshot.candidate != candidate
            or snapshot.reference_pack is None
            or snapshot.reference_pack.pin != candidate.reference_pack
        ):
            raise StaleStateError(message="Reload the candidate's exact captured pack")
        return snapshot

    @override
    async def add_report(self, *, report: ValidationReport) -> None:
        self._session.add(
            _ValidationRow(
                project_id=report.scope.project_id.value,
                model_id=report.scope.model_id.value,
                id=report.id.value,
                candidate_id=report.candidate_id.value,
                report=record_bytes(value=report),
            )
        )
        await self._session.flush()
