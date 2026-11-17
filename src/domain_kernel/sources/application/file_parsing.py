"""Bound parser output and keep exact source citations separate from derived metadata."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.shared.errors import ResourceLimitError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.validation import require_exact, require_text
from domain_kernel.sources.application.contracts import CSV
from domain_kernel.sources.application.parsed_sources import resolved_content
from domain_kernel.sources.domain.errors.evidence_unavailable_error import EvidenceUnavailableError
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.models import Evidence, SourceProfile
from domain_kernel.sources.domain.parsed import CellRange, ParsedTable
from domain_kernel.sources.domain.tables import profile_table

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from domain_kernel.sources.application.contracts import FileDescriptor
    from domain_kernel.sources.application.ports import AcquiredSource, FormatParser
    from domain_kernel.sources.domain.models import (
        EvidenceContent,
        ProcessingLimits,
        ProcessingRecord,
    )


_MAX_SECTION_LABEL = 512
_SAMPLE_ROWS = 16


@dataclass(frozen=True, kw_only=True)
class FileParsing:
    """Bounded detached output of one parser invocation."""

    pages: int | None
    sections: tuple[str, ...]
    tables: tuple[ParsedTable, ...]

    def capture(
        self, *, processing: ProcessingRecord, descriptor: FileDescriptor
    ) -> tuple[SourceProfile, tuple[Evidence, ...]]:
        """Store an inventory and bounded citations, with rows available on explicit request."""
        if self.tables:
            processing = replace(
                processing,
                parser_options=descriptor.model_dump_json(
                    exclude={"path", "location", "expected_hash"}
                ),
            )
        profile = SourceProfile(
            source=processing.source,
            processing=processing,
            page_count=self.pages,
            sections=self.sections,
            tables=tuple(
                profile_table(table=table, text_scalars=isinstance(descriptor, CSV))
                for table in self.tables
            ),
        )
        evidence = tuple(
            _cite(processing=processing, locator=locator)
            for table in self.tables
            for locator in table.row_locators[:_SAMPLE_ROWS]
            if isinstance(locator, CellRange)
        )
        return profile, evidence

    def resolve(self, *, evidence: Evidence) -> EvidenceContent:
        """Find the exact sample row returned by the recorded parser."""
        for table in self.tables:
            if evidence.locator in table.row_locators:
                position = table.row_locators.index(evidence.locator)
                return resolved_content(
                    evidence=evidence,
                    part=replace(
                        table,
                        rows=(table.rows[position],),
                        locator=evidence.locator,
                        row_locators=(),
                    ),
                )
        raise EvidenceUnavailableError


def _cite(*, processing: ProcessingRecord, locator: CellRange) -> Evidence:
    source = processing.source
    return Evidence(
        id=EvidenceId(
            hash_json(
                value=record_value(
                    value=(
                        source.project_id,
                        source.source_id,
                        source.revision_id,
                        processing.fingerprint,
                        locator,
                    )
                )
            ).value
        ),
        source=source,
        locator=locator,
        processing=processing,
    )


def _text_bytes(*, text: str, remaining: int) -> int:
    total = 0
    for offset in range(0, len(text), 8192):
        total += len(text[offset : offset + 8192].encode())
        if total > remaining:
            raise ResourceLimitError(message="Keep expanded content within the configured limit")
    return total


def _table_text_bytes(*, table: ParsedTable, remaining: int) -> int:
    total = sum(_text_bytes(text=name, remaining=remaining) for name in table.columns)
    for row in table.rows:
        for cell in row:
            if isinstance(cell, str):
                total += _text_bytes(text=cell, remaining=remaining - total)
    if total > remaining:
        raise ResourceLimitError(message="Keep expanded content within the configured limit")
    return total


def _validate_table(*, table: ParsedTable, seen: Sequence[ParsedTable]) -> None:
    if (
        not isinstance(table.locator, CellRange)
        or len(table.row_locators) != len(table.rows)
        or any(not isinstance(item, CellRange) for item in table.row_locators)
        or any(item.name == table.name for item in seen)
    ):
        raise ValueError("Supply distinct tables with exact sheet and row coordinates")


def parse_file(
    *,
    parser: FormatParser,
    acquired: AcquiredSource,
    descriptor: FileDescriptor,
    limits: ProcessingLimits,
) -> FileParsing:
    """Apply shared limits to all configured parser implementations."""
    expanded = cell_count = 0
    pages: set[int] = set()
    sections: dict[str, None] = {}
    tables: list[ParsedTable] = []
    for chunk in parser.parse(content=acquired, descriptor=descriptor, limits=limits):
        if isinstance(chunk, ParsedTable):
            _validate_table(table=chunk, seen=tables)
            cell_count += (len(chunk.rows) + 1) * len(chunk.columns)
            if cell_count > limits.max_table_cells or len(tables) >= limits.max_tables:
                raise ResourceLimitError(message="Keep parsed tables within configured limits")
            expanded += _table_text_bytes(
                table=chunk, remaining=limits.max_expanded_bytes - expanded
            )
            tables.append(chunk)
            continue
        require_text(value=chunk.text, field="Parsed text")
        expanded += _text_bytes(text=chunk.text, remaining=limits.max_expanded_bytes - expanded)
        if chunk.page is not None:
            require_exact(value=chunk.page, expected=int, field="Parsed page")
            if chunk.page < 1 or chunk.page > limits.max_pages:
                raise ResourceLimitError(message="Keep parsed pages within the configured limit")
            pages.add(chunk.page)
        if chunk.section is not None:
            require_text(value=chunk.section, field="Parsed section")
            if len(chunk.section) > _MAX_SECTION_LABEL:
                raise ResourceLimitError(message="Use bounded labels for parsed sections")
            sections[chunk.section] = None
    return FileParsing(pages=len(pages) or None, sections=tuple(sections), tables=tuple(tables))


async def run_parser[T](*, parse: Callable[[], T]) -> T:
    """Wait for the bounded parser to release the acquired buffer during cancellation."""
    work = asyncio.create_task(asyncio.to_thread(parse))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        with suppress(Exception):
            _ = await work
        raise
