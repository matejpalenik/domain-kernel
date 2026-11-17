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
from domain_kernel.sources.application.parsed_sources import (
    part_at,
    resolve_excerpt,
    resolved_content,
)
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.models import (
    Evidence,
    RetainedDocument,
    RetainedExcerpt,
    SourceProfile,
)
from domain_kernel.sources.domain.parsed import CellRange, DocumentSpan, ParsedTable, ParsedText
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
    from domain_kernel.sources.domain.parsed import EvidenceLocator


_MAX_SECTION_LABEL = 512
_SAMPLE_ROWS = 16


@dataclass(frozen=True, kw_only=True)
class FileParsing:
    """Bounded detached output of one parser invocation."""

    pages: int | None
    sections: tuple[str, ...]
    tables: tuple[ParsedTable, ...]
    texts: tuple[ParsedText, ...]

    def capture(
        self, *, processing: ProcessingRecord, descriptor: FileDescriptor
    ) -> tuple[SourceProfile, tuple[Evidence, ...]]:
        """Store an inventory and bounded citations, with rows available on explicit request."""
        if self.tables or self.texts:
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
        locators = [part.locator for part in self.texts]
        for table in self.tables:
            if isinstance(table.locator, DocumentSpan):
                locators.append(table.locator)
            else:
                locators.extend(table.row_locators[:_SAMPLE_ROWS])
        evidence = tuple(_cite(processing=processing, locator=locator) for locator in locators)
        return profile, evidence

    def retained_document(self, *, processing: ProcessingRecord) -> RetainedDocument | None:
        """Retain document text and tables only when requested by source processing."""
        parts = (
            *self.texts,
            *(part for part in self.tables if isinstance(part.locator, DocumentSpan)),
        )
        if not parts:
            return None
        return RetainedDocument(
            source=processing.source,
            fingerprint=processing.fingerprint,
            parts=parts,
        )

    def resolve(self, *, evidence: Evidence) -> EvidenceContent:
        """Find the exact normalized part returned by the recorded parser."""
        return resolve_parts(evidence=evidence, parts=(*self.texts, *self.tables))


def resolve_parts(
    *, evidence: Evidence, parts: Sequence[ParsedText | ParsedTable]
) -> EvidenceContent:
    """Resolve a file citation to its exact normalized part or table row."""
    return resolved_content(
        evidence=evidence,
        part=part_at(parts=parts, locator=evidence.locator),
    )


def resolve_document(
    *,
    evidence: Evidence,
    document: RetainedDocument,
    limits: ProcessingLimits,
) -> EvidenceContent:
    """Check the retained processing capture before resolving its cited part."""
    if (
        document.source != evidence.source
        or document.fingerprint != evidence.processing.fingerprint
    ):
        raise SourceRevisionMismatchError
    excerpt = RetainedExcerpt(
        evidence=evidence,
        part=part_at(parts=document.parts, locator=evidence.locator),
    )
    return resolve_excerpt(evidence=evidence, excerpt=excerpt, limits=limits)


def _cite(*, processing: ProcessingRecord, locator: EvidenceLocator) -> Evidence:
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
    if isinstance(table.locator, CellRange):
        if len(table.row_locators) != len(table.rows) or any(
            not isinstance(item, CellRange) or item.sheet != table.locator.sheet
            for item in table.row_locators
        ):
            raise ValueError("Supply exact spreadsheet row coordinates")
    elif not isinstance(table.locator, DocumentSpan):
        raise TypeError("Use an exact table locator")
    if any(item.name == table.name for item in seen):
        raise ValueError("Use distinct table names")


def _observe_location(
    *,
    page: int | None,
    section: str | None,
    limits: ProcessingLimits,
    pages: set[int],
    sections: dict[str, None],
) -> None:
    if page is not None:
        require_exact(value=page, expected=int, field="Parsed page")
        if page < 1 or page > limits.max_pages:
            raise ResourceLimitError(message="Keep parsed pages within the configured limit")
        pages.add(page)
    if section is not None:
        require_text(value=section, field="Parsed section")
        if len(section) > _MAX_SECTION_LABEL:
            raise ResourceLimitError(message="Use bounded labels for parsed sections")
        sections[section] = None


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
    texts: list[ParsedText] = []
    for chunk in parser.parse(content=acquired, descriptor=descriptor, limits=limits):
        if isinstance(chunk, ParsedTable):
            _validate_table(table=chunk, seen=tables)
            if isinstance(chunk.locator, DocumentSpan):
                _observe_location(
                    page=chunk.locator.page,
                    section=chunk.locator.section,
                    limits=limits,
                    pages=pages,
                    sections=sections,
                )
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
        if isinstance(chunk, ParsedText):
            locator = chunk.locator
            if not isinstance(locator, DocumentSpan):
                raise TypeError("Use an exact document span for parsed text")
            _observe_location(
                page=locator.page,
                section=locator.section,
                limits=limits,
                pages=pages,
                sections=sections,
            )
            texts.append(chunk)
        else:
            _observe_location(
                page=chunk.page,
                section=chunk.section,
                limits=limits,
                pages=pages,
                sections=sections,
            )
    return FileParsing(
        pages=len(pages) or None,
        sections=tuple(sections),
        tables=tuple(tables),
        texts=tuple(texts),
    )


async def run_parser[T](*, parse: Callable[[], T]) -> T:
    """Wait for the bounded parser to release the acquired buffer during cancellation."""
    work = asyncio.create_task(asyncio.to_thread(parse))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        with suppress(Exception):
            _ = await work
        raise
