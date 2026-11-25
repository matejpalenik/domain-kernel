"""Persist exact extraction snapshots and their typed drafts in SQLite."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import batched
from math import ceil
from typing import TYPE_CHECKING, final, override
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import ForeignKeyConstraint, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.discovery.application.ports import ExtractionRepository
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.models import DiscoveryDraft
from domain_kernel.shared.errors import StaleStateError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.discovery.domain.models import ExtractionIntent, Proposal
    from domain_kernel.shared.contracts import ModelScope


@final
class _ExtractionRow(SQLiteBase):
    __tablename__ = "dk_extraction"
    __table_args__: tuple[ForeignKeyConstraint, ...] = (
        ForeignKeyConstraint(["project_id", "model_id"], ["dk_model.project_id", "dk_model.id"]),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    identity: Mapped[str] = mapped_column(String, primary_key=True)
    intent: Mapped[bytes] = mapped_column(LargeBinary)
    result: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


@dataclass(frozen=True, kw_only=True)
class _ProposalBatch:
    draft_id: DiscoveryDraftId
    ordinal: int
    proposals: tuple[Proposal, ...]


@dataclass(frozen=True, kw_only=True)
class _BatchedDraft:
    draft: DiscoveryDraft
    count: int
    batch_count: int


def _batch_id(*, draft_id: DiscoveryDraftId, ordinal: int) -> DiscoveryDraftId:
    # Private batch records reuse the extraction table so existing workspaces can opt in.
    return DiscoveryDraftId(
        str(uuid5(NAMESPACE_URL, f"domain-kernel:draft:{draft_id.value}:batch:{ordinal}"))
    )


@final
class SQLiteExtraction(ExtractionRepository):
    """Use an operation-local session for exact scoped drafts."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind a shared session without opening a transaction."""
        self._session = session

    @override
    async def reserve(self, *, intent: ExtractionIntent) -> None:
        scope = intent.context.scope
        self._session.add(
            _ExtractionRow(
                project_id=scope.project_id.value,
                model_id=scope.model_id.value,
                identity=intent.id.value,
                intent=record_bytes(value=intent),
                result=None,
            ),
        )
        await self._session.flush()

    @override
    async def complete(self, *, draft: DiscoveryDraft, batch_size: int | None = None) -> None:
        saved = await self._row(identifier=draft.id, scope=draft.scope)
        if saved is None or saved.result is not None:
            raise StaleStateError(message="Reload the exact pending extraction capture.")
        if batch_size is None or not draft.proposals:
            saved.result = record_bytes(value=draft)
        else:
            header = _BatchedDraft(
                draft=replace(draft, proposals=()),
                count=len(draft.proposals),
                batch_count=ceil(len(draft.proposals) / batch_size),
            )
            saved.result = record_bytes(value=header, root_type=_BatchedDraft)
            for ordinal, group in enumerate(batched(draft.proposals, batch_size, strict=False)):
                self._session.add(
                    _ExtractionRow(
                        project_id=saved.project_id,
                        model_id=saved.model_id,
                        identity=_batch_id(draft_id=draft.id, ordinal=ordinal).value,
                        intent=saved.intent,
                        result=record_bytes(
                            value=_ProposalBatch(
                                draft_id=draft.id, ordinal=ordinal, proposals=group
                            ),
                            root_type=_ProposalBatch,
                        ),
                    )
                )
        await self._session.flush()

    @override
    async def draft(self, *, identifier: DiscoveryDraftId, scope: ModelScope) -> DiscoveryDraft:
        saved = await self._row(identifier=identifier, scope=scope)
        if saved is None or saved.result is None:
            raise StaleStateError(message="Reload a completed extraction capture.")
        try:
            return read_record(content=saved.result, expected=DiscoveryDraft)
        except ValueError:
            header = read_record(
                content=saved.result, expected=_BatchedDraft, root_type=_BatchedDraft
            )
        if header.draft.id != identifier or header.draft.scope != scope:
            raise StaleStateError(message="Reload the exact completed extraction capture.")
        proposals: list[Proposal] = []
        for ordinal in range(header.batch_count):
            batch = await self._row(
                identifier=_batch_id(draft_id=identifier, ordinal=ordinal), scope=scope
            )
            if batch is None or batch.result is None or batch.intent != saved.intent:
                raise StaleStateError(message="Inspect the incomplete proposal batch inventory.")
            record = read_record(
                content=batch.result, expected=_ProposalBatch, root_type=_ProposalBatch
            )
            if record.draft_id != identifier or record.ordinal != ordinal:
                raise StaleStateError(message="Inspect the proposal batch order.")
            proposals.extend(record.proposals)
        if len(proposals) != header.count:
            raise StaleStateError(message="Inspect the incomplete saved proposal count.")
        return replace(header.draft, proposals=tuple(proposals))

    async def _row(
        self,
        *,
        identifier: DiscoveryDraftId,
        scope: ModelScope,
    ) -> _ExtractionRow | None:
        return await self._session.get(
            _ExtractionRow,
            (scope.project_id.value, scope.model_id.value, identifier.value),
        )
