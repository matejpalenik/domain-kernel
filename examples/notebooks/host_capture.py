"""Load the labelled source-checked captures supplied by the tour's example host."""

from __future__ import annotations

import csv
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, final

from domain_kernel import (
    CellRange,
    ContentHash,
    ExternalLocation,
    Iri,
    OntologyStatement,
    ParsedGraph,
    ParsedPayload,
    ParsedSourceOrigin,
    ParsedSourceProvider,
    ParsedTable,
    ParsedText,
    SourceUnavailableError,
)
from examples.notebooks._preview.catalogue import load_sources

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from domain_kernel import ProcessingLimits
    from examples.notebooks._preview.catalogue import SourceRecord

_PROVIDER = "recruitment-capture-host"
_CAPTURED = datetime(2026, 11, 15, 15, 37, tzinfo=UTC)


def _origin(*, source: SourceRecord, document: str) -> ParsedSourceOrigin:
    if source.sha256 is None:
        raise ValueError("Select a source with a recorded original digest")
    return ParsedSourceOrigin(
        provider=_PROVIDER,
        document_id=document,
        document_revision=source.edition,
        captured_at=_CAPTURED,
        claimed_original_digest=ContentHash(value=f"sha256:{source.sha256}"),
    )


@final
class _FixtureResolver:
    def __init__(self, *, captures: tuple[ParsedPayload, ...]) -> None:
        self._captures = {item.origin: item for item in captures}

    @asynccontextmanager
    async def open(
        self,
        *,
        origin: ParsedSourceOrigin,
        limits: ProcessingLimits,
    ) -> AsyncGenerator[ParsedPayload]:
        del limits  # The SDK independently enforces bounds before exposing the supplied part.
        capture = self._captures.get(origin)
        if capture is None:
            raise SourceUnavailableError
        yield capture


def example_host() -> tuple[ParsedSourceProvider, tuple[ParsedPayload, ...]]:
    """Bind the real source-selected derivative excerpts to one caller-owned provider."""
    sources = {item.id: item for item in load_sources()}
    act = sources["ai-act-en"]
    excerpt = next(item for item in act.passages if item.id == "ai-13-instructions")
    passage = ParsedPayload(
        origin=_origin(source=act, document="ai-act-instructions-capture"),
        parts=[ParsedText(text=excerpt.text, locator=ExternalLocation(key=excerpt.id))],
    )
    path = Path(__file__).parent / "fixtures/eli-metadata-selection.csv"
    with path.open(newline="", encoding="utf-8") as source:
        rows = tuple(tuple(row) for row in csv.reader(source))
    table = ParsedPayload(
        origin=_origin(source=sources["eli-workbook"], document="eli-metadata-capture"),
        parts=[
            ParsedTable(
                name="ELI metadata selection",
                columns=rows[0],
                rows=rows[1:],
                locator=ExternalLocation(key="eli-metadata-selection"),
                row_locators=[CellRange(sheet=row[2], cells=row[3]) for row in rows[1:]],
            ),
        ],
    )
    eli = sources["eli"]
    verified_iri = next(item.locator for item in eli.passages if item.id == "eli-1")
    graph = ParsedPayload(
        origin=_origin(source=eli, document="eli-legal-resource-capture"),
        parts=[
            ParsedGraph(
                locator=ExternalLocation(key="eli-legal-resource-class"),
                statements=[
                    OntologyStatement(
                        subject=Iri(value=verified_iri),
                        predicate=Iri(value="http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                        object=Iri(value="http://www.w3.org/2002/07/owl#Class"),
                    ),
                ],
            ),
        ],
    )
    captures = (passage, table, graph)
    return ParsedSourceProvider(
        name=_PROVIDER, resolver=_FixtureResolver(captures=captures)
    ), captures
