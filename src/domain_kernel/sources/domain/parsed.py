"""Exact caller-supplied text, tables, and graph captures."""

from __future__ import annotations

import re
from collections.abc import Sequence  # noqa: TC003 - Capture descriptors reflect this schema.
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from typing import Literal

from domain_kernel._shared.domain.rdf import OntologyStatement
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import (
    is_non_string_sequence,
    require_exact,
    require_text,
    snapshot_sequence,
)


@dataclass(frozen=True, kw_only=True)
class ParsedSourceOrigin:
    """An upstream capture identity and host-supplied provenance."""

    provider: str
    document_id: str
    document_revision: str
    captured_at: datetime
    claimed_original_digest: ContentHash | None = None
    kind: Literal["supplied"] = "supplied"

    def __post_init__(self) -> None:
        """Keep an exact upstream identity and a timezone-aware capture time."""
        require_text(value=self.provider, field="Provider name")
        require_text(value=self.document_id, field="Upstream document ID")
        require_text(value=self.document_revision, field="Upstream document revision")
        require_exact(value=self.captured_at, expected=datetime, field="Capture time")
        require_exact(value=self.kind, expected=str, field="Origin kind")
        if self.kind != "supplied" or self.captured_at.utcoffset() is None:
            raise ValueError("Use the supplied origin kind and an attributed time zone")
        if self.claimed_original_digest is not None:
            require_exact(
                value=self.claimed_original_digest,
                expected=ContentHash,
                field="Claimed original hash",
            )


@dataclass(frozen=True, kw_only=True)
class ExternalLocation:
    """A stable opaque host locator that the SDK never dereferences."""

    key: str
    kind: Literal["external"] = "external"

    def __post_init__(self) -> None:
        """Capture a case-sensitive locator string and exact tag."""
        require_text(value=self.key, field="External locator key")
        require_exact(value=self.kind, expected=str, field="Locator kind")
        if self.kind != "external":
            raise ValueError("Use the external locator discriminator")


@dataclass(frozen=True, kw_only=True)
class DocumentSpan:
    """Offsets in the supplied document section or page."""

    start: int
    end: int
    page: int | None = None
    section: str | None = None
    kind: Literal["document_span"] = "document_span"

    def __post_init__(self) -> None:
        """Validate ordered nonnegative offsets and optional page coordinates."""
        require_exact(value=self.start, expected=int, field="Span start")
        require_exact(value=self.end, expected=int, field="Span end")
        require_exact(value=self.kind, expected=str, field="Span kind")
        if self.start < 0 or self.end <= self.start or self.kind != "document_span":
            raise ValueError("Use a nonempty document span and its declared kind")
        if self.page is not None:
            require_exact(value=self.page, expected=int, field="Page number")
            if self.page < 1:
                raise ValueError("Use a positive page number")
        if self.section is not None:
            require_text(value=self.section, field="Section name")


_CELL_RANGE = re.compile(r"\$?[A-Z]+\$?[1-9]\d*(?::\$?[A-Z]+\$?[1-9]\d*)?")


@dataclass(frozen=True, kw_only=True)
class CellRange:
    """A range in a specified upstream sheet."""

    sheet: str
    cells: str
    kind: Literal["cells"] = "cells"

    def __post_init__(self) -> None:
        """Check the exact sheet name and A1 range spelling."""
        require_text(value=self.sheet, field="Sheet name")
        require_text(value=self.cells, field="Cell range")
        require_exact(value=self.kind, expected=str, field="Range kind")
        if _CELL_RANGE.fullmatch(self.cells) is None or self.kind != "cells":
            raise ValueError("Use an A1 cell range and the declared locator kind")


@dataclass(frozen=True, kw_only=True)
class StatementSpan:
    """Character offsets within the captured statement."""

    start: int
    end: int
    kind: Literal["statement_span"] = "statement_span"

    def __post_init__(self) -> None:
        """Require a nonempty exact interval."""
        require_exact(value=self.start, expected=int, field="Statement span start")
        require_exact(value=self.end, expected=int, field="Statement span end")
        require_exact(value=self.kind, expected=str, field="Statement span kind")
        if self.start < 0 or self.end <= self.start or self.kind != "statement_span":
            raise ValueError("Use a nonempty statement span and its declared kind")


type EvidenceLocator = ExternalLocation | DocumentSpan | CellRange | StatementSpan
type CellValue = bool | int | float | str | date | datetime | Decimal | None

_LOCATOR_TYPES = (ExternalLocation, DocumentSpan, CellRange, StatementSpan)
_CELL_TYPES = (type(None), bool, int, float, str, date, datetime, Decimal)


def require_locator(*, locator: EvidenceLocator) -> None:
    """Require a closed nominal locator without following it."""
    if type(locator) not in _LOCATOR_TYPES:
        raise TypeError("Choose one supported exact evidence locator")


def _sequence[T](*, items: Sequence[T], field_name: str) -> tuple[T, ...]:
    if not is_non_string_sequence(items):
        message = f"Use a sequence for {field_name}."
        raise TypeError(message)
    return tuple(items)


@dataclass(frozen=True, kw_only=True)
class ParsedText:
    """An explicitly supplied text excerpt and its stable locator."""

    text: str = field(repr=False)
    locator: EvidenceLocator
    kind: Literal["text"] = "text"

    def __post_init__(self) -> None:
        """Bind nonempty content to one exact locator."""
        require_text(value=self.text, field="Supplied text")
        require_locator(locator=self.locator)
        require_exact(value=self.kind, expected=str, field="Text kind")
        if self.kind != "text":
            raise ValueError("Use the supplied text discriminator")


def _check_cells(*, row: Sequence[CellValue]) -> None:
    for item in row:
        if type(item) not in _CELL_TYPES:
            raise TypeError("Use a supported exact table scalar")
        if isinstance(item, float) and not isfinite(item):
            raise ValueError("Use finite floating point values")
        if isinstance(item, Decimal) and not item.is_finite():
            raise ValueError("Use finite decimal values")
        if isinstance(item, datetime) and item.utcoffset() is None:
            raise ValueError("Use a timezone-aware timestamp")


@dataclass(frozen=True, kw_only=True)
class ParsedTable:
    """An explicitly supplied rectangular table."""

    name: str
    columns: Sequence[str]
    rows: Sequence[Sequence[CellValue]] = field(repr=False)
    locator: EvidenceLocator
    row_locators: Sequence[EvidenceLocator] = ()
    kind: Literal["table"] = "table"

    def __post_init__(self) -> None:
        """Freeze typed values and require exact column and row locations."""
        require_text(value=self.name, field="Table name")
        require_locator(locator=self.locator)
        require_exact(value=self.kind, expected=str, field="Table kind")
        columns = snapshot_sequence(items=self.columns, item_type=str, field="Table columns")
        if not columns or len(set(columns)) != len(columns) or self.kind != "table":
            raise ValueError("Use distinct table columns and the table discriminator")
        for heading in columns:
            require_text(value=heading, field="Column name")
        rows = tuple(
            _sequence(items=item, field_name="table cells")
            for item in _sequence(items=self.rows, field_name="table rows")
        )
        for row in rows:
            if len(row) != len(columns):
                raise ValueError("Supply rectangular table rows")
            _check_cells(row=row)
        locators = _sequence(items=self.row_locators, field_name="row locators")
        for locator in locators:
            require_locator(locator=locator)
        if locators and (
            len(locators) != len(rows)
            or len(set(locators)) != len(locators)
            or self.locator in locators
        ):
            raise ValueError("Supply one distinct locator per row")
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "row_locators", locators)


@dataclass(frozen=True, kw_only=True)
class ParsedGraph:
    """An exact graph fragment supplied as evidence by the host."""

    statements: Sequence[OntologyStatement] = field(repr=False)
    locator: EvidenceLocator
    kind: Literal["graph"] = "graph"

    def __post_init__(self) -> None:
        """Bind a nonempty typed statement sequence and its exact locator."""
        items = snapshot_sequence(
            items=self.statements,
            item_type=OntologyStatement,
            field="Supplied statements",
        )
        require_locator(locator=self.locator)
        require_exact(value=self.kind, expected=str, field="Graph kind")
        if not items or self.kind != "graph":
            raise ValueError("Supply at least one graph statement and the graph discriminator")
        object.__setattr__(self, "statements", items)


type ParsedPart = ParsedText | ParsedTable | ParsedGraph


@dataclass(frozen=True, kw_only=True)
class ParsedPayload:
    """The versioned host content used for capture and exact resolution."""

    origin: ParsedSourceOrigin
    parts: Sequence[ParsedPart] = field(repr=False)
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Detach a complete capture and forbid ambiguous locator identities."""
        require_exact(value=self.origin, expected=ParsedSourceOrigin, field="Supplied origin")
        require_exact(value=self.schema_version, expected=int, field="Capture schema")
        parts = _sequence(items=self.parts, field_name="supplied parts")
        if not parts or self.schema_version != 1:
            raise ValueError("Supply at least one part using the supported capture schema")
        locators: set[EvidenceLocator] = set()
        for part in parts:
            if type(part) not in (ParsedText, ParsedTable, ParsedGraph):
                raise TypeError("Supply a supported typed capture part")
            keys = (
                (part.locator, *part.row_locators)
                if isinstance(part, ParsedTable)
                else (part.locator,)
            )
            if locators.intersection(keys):
                raise ValueError("Use one unique locator for each part and table row")
            locators.update(keys)
        object.__setattr__(self, "parts", parts)
