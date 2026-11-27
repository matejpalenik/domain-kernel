"""Bound parser output and keep exact source citations separate from derived metadata."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, replace
from time import perf_counter
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.application.contracts import document_kind
from domain_kernel.sources.application.parsed_sources import (
    part_at,
    resolve_excerpt,
    resolved_content,
)
from domain_kernel.sources.domain.coverage import CoverageStatus, CoverageUnit
from domain_kernel.sources.domain.document_formats import DocumentFormat
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
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FileParsing:
    """Bounded detached output of one parser invocation."""

    pages: int | None
    sections: tuple[str, ...]
    tables: tuple[ParsedTable, ...]
    texts: tuple[ParsedText, ...]
    coverage: tuple[CoverageUnit, ...]

    def capture_fingerprint(self, *, configuration_fingerprint: str) -> str:
        """Give interrupted captures an identity distinct from a complete reprocessing."""
        deferred = tuple(unit for unit in self.coverage if unit.status is CoverageStatus.DEFERRED)
        if not deferred:
            return configuration_fingerprint
        return Hashing.hash_json(
            value=(
                "deferred-source-capture-v1",
                configuration_fingerprint,
                RecordCodec.to_value(value=deferred),
                tuple(
                    Hashing.hash_json(value=RecordCodec.to_value(value=part)).value
                    for part in (*self.texts, *self.tables)
                ),
            )
        ).value

    def capture(
        self, *, processing: ProcessingRecord, descriptor: FileDescriptor
    ) -> tuple[SourceProfile, tuple[Evidence, ...]]:
        """Store the coverage inventory and exact citations for the selected content."""
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
                profile_table(
                    table=table,
                    text_scalars=document_kind(descriptor=descriptor) is DocumentFormat.CSV,
                )
                for table in self.tables
            ),
            coverage=self.coverage,
        )
        locators = [part.locator for part in self.texts]
        for table in self.tables:
            if isinstance(table.locator, DocumentSpan):
                locators.append(table.locator)
            else:
                locators.extend(table.row_locators)
        evidence = tuple(_cite(processing=processing, locator=locator) for locator in locators)
        return profile, evidence

    def retained_document(self, *, processing: ProcessingRecord) -> RetainedDocument | None:
        """Retain document text and tables only when requested by source processing."""
        parts = (*self.texts, *self.tables)
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
            Hashing.hash_json(
                value=RecordCodec.to_value(
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
        RuntimeTypeValidation.require_exact(value=page, expected=int, field="Parsed page")
        if page < 1 or page > limits.max_pages:
            raise ResourceLimitError(message="Keep parsed pages within the configured limit")
        pages.add(page)
    if section is not None:
        TextValidation.require_text(value=section, field="Parsed section")
        if len(section) > _MAX_SECTION_LABEL:
            raise ResourceLimitError(message="Use bounded labels for parsed sections")
        sections[section] = None


def _complete_coverage(
    *,
    explicit: dict[EvidenceLocator, CoverageUnit],
    texts: Sequence[ParsedText],
    tables: Sequence[ParsedTable],
) -> tuple[CoverageUnit, ...]:
    locators = [
        part.locator
        for part in texts
        if not (
            isinstance(part.locator, DocumentSpan)
            and (part.locator.section or "").startswith("docling-chunk/")
        )
    ]
    for table in tables:
        locators.extend(table.row_locators or (table.locator,))
    for locator in locators:
        if locator not in explicit:
            explicit[locator] = CoverageUnit(locator=locator, status=CoverageStatus.PROCESSED)
    return tuple(explicit.values())


def parse_file(
    *,
    parser: FormatParser,
    acquired: AcquiredSource,
    descriptor: FileDescriptor,
    limits: ProcessingLimits,
    reparse: bool = False,
) -> FileParsing:
    """Apply shared limits to all configured parser implementations."""
    started = perf_counter()
    expanded = cell_count = 0
    pages: set[int] = set()
    sections: dict[str, None] = {}
    tables: list[ParsedTable] = []
    texts: list[ParsedText] = []
    explicit: dict[EvidenceLocator, CoverageUnit] = {}
    for chunk in parser.parse(content=acquired, descriptor=descriptor, limits=limits):
        if isinstance(chunk, CoverageUnit):
            explicit[chunk.locator] = chunk
            if isinstance(chunk.locator, DocumentSpan):
                _observe_location(
                    page=chunk.locator.page,
                    section=None,
                    limits=limits,
                    pages=pages,
                    sections=sections,
                )
            continue
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
        TextValidation.require_text(value=chunk.text, field="Parsed text")
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
    coverage = _complete_coverage(explicit=explicit, texts=texts, tables=tables)
    _LOGGER.debug(
        "Parsed %s in %.3f seconds with %d/%d processed units (reparse=%s)",
        document_kind(descriptor=descriptor) or descriptor.format,
        perf_counter() - started,
        sum(unit.status is CoverageStatus.PROCESSED for unit in coverage),
        len(coverage),
        reparse,
    )
    return FileParsing(
        pages=len(pages) or None,
        sections=tuple(sections),
        tables=tuple(tables),
        texts=tuple(texts),
        coverage=coverage,
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
