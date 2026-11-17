"""Optional adapters for verified tabular sources."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO, StringIO
from typing import TYPE_CHECKING, Protocol, Self, final, override, runtime_checkable
from zipfile import BadZipFile, ZipFile

from domain_kernel.shared.errors import MissingCapabilityError, ResourceLimitError, SourceReadError
from domain_kernel.sources.application.contracts import CSV, Excel
from domain_kernel.sources.application.ports import FormatParser
from domain_kernel.sources.domain.parsed import CellRange, CellValue, ParsedTable

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from types import TracebackType
    from typing import IO
    from xml.etree.ElementTree import Element

    from domain_kernel.sources.application.contracts import FileDescriptor
    from domain_kernel.sources.application.ports import AcquiredSource
    from domain_kernel.sources.domain.models import ProcessingLimits


_MISSING_EXTRA = "Install the Domain Kernel tabular extra."
_XLSX_ROW_CAP = 1_048_576
_XLSX_COLUMN_CAP = 16_384
_CELL = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")
_WORKSHEET = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _version(*, distribution: str) -> str:
    try:
        return version(distribution_name=distribution)
    except PackageNotFoundError:
        raise MissingCapabilityError(message=_MISSING_EXTRA) from None


def _load(*, module: str) -> object:
    try:
        return import_module(name=module)
    except ImportError:
        raise MissingCapabilityError(message=_MISSING_EXTRA) from None


class _CSVRelation(Protocol):
    @property
    def columns(self) -> list[str]: ...
    def limit(self, count: int, /) -> _CSVRelation: ...
    def fetchall(self) -> list[tuple[str | None, ...]]: ...


class _DuckConnection(Protocol):
    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        error: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None: ...
    def read_csv(  # noqa: PLR0913 - Exact external adapter arguments.
        self,
        source: StringIO,
        /,
        *,
        header: bool,
        delimiter: str,
        all_varchar: bool,
        strict_mode: bool,
        quotechar: str,
        escapechar: str,
        null_padding: bool,
        allow_quoted_nulls: bool,
        skiprows: int,
        max_line_size: int,
    ) -> _CSVRelation: ...


@runtime_checkable
class _DuckDB(Protocol):
    @property
    def Error(self) -> type[Exception]: ...  # noqa: N802 - DuckDB exception type.
    @property
    def OutOfMemoryException(self) -> type[Exception]: ...  # noqa: N802 - DuckDB exception type.
    def connect(self, *, config: dict[str, str]) -> _DuckConnection: ...


class _Sheet(Protocol):
    @property
    def title(self) -> str: ...
    def reset_dimensions(self) -> None: ...
    def iter_rows(self, *, values_only: bool) -> Iterator[tuple[object, ...]]: ...


class _Workbook(Protocol):
    @property
    def worksheets(self) -> list[_Sheet]: ...
    def close(self) -> None: ...


@runtime_checkable
class _Openpyxl(Protocol):
    def load_workbook(
        self, *, filename: BytesIO, read_only: bool, data_only: bool, keep_links: bool
    ) -> _Workbook: ...


@runtime_checkable
class _SafeXML(Protocol):
    def iterparse(
        self,
        *,
        source: IO[bytes],
        events: tuple[str, ...],
        forbid_dtd: bool,
    ) -> Iterator[tuple[str, Element]]: ...


def _column_name(*, number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _headings(*, header: Sequence[CellValue], width: int) -> tuple[str, ...]:
    headings: list[str] = []
    occupied: set[str] = set()
    for position in range(width):
        value = header[position] if position < len(header) else None
        coordinate = _column_name(number=position + 1)
        heading = (str(value).strip() if value is not None else "") or coordinate
        while heading in occupied:
            heading = f"{heading} ({coordinate})"
        headings.append(heading)
        occupied.add(heading)
    return tuple(headings)


def _range(*, name: str, start: int, stop: int, width: int) -> CellRange:
    first = f"A{start}"
    last = f"{_column_name(number=width)}{stop}"
    return CellRange(sheet=name, cells=first if first == last else f"{first}:{last}")


def _table(
    *,
    name: str,
    header_row: int,
    width: int,
    header: Sequence[CellValue],
    rows: Sequence[tuple[int, Sequence[CellValue]]],
) -> ParsedTable:
    return ParsedTable(
        name=name,
        columns=_headings(header=header, width=width),
        rows=tuple(tuple(cells) + (None,) * (width - len(cells)) for _, cells in rows),
        locator=_range(
            name=name, start=header_row, stop=rows[-1][0] if rows else header_row, width=width
        ),
        row_locators=tuple(
            _range(name=name, start=position, stop=position, width=width) for position, _ in rows
        ),
    )


def _read(*, content: AcquiredSource, limits: ProcessingLimits) -> bytes:
    raw = content.stream.read(size=limits.max_source_bytes + 1)
    if len(raw) > limits.max_source_bytes:
        raise ResourceLimitError
    return raw


def _decode_csv(*, raw: bytes, encoding: str, limits: ProcessingLimits) -> str:
    try:
        decoded = raw.decode(encoding=encoding)
    except (LookupError, UnicodeError):
        raise SourceReadError(message="Choose the CSV's declared text encoding.") from None
    if len(decoded.encode()) > limits.max_expanded_bytes:
        raise ResourceLimitError(message="Keep decoded CSV bytes within the configured limit.")
    if "\0" in decoded:
        raise SourceReadError(message="Supply CSV text without NUL characters.")
    return decoded


def _read_csv(
    *,
    duckdb: _DuckDB,
    text: str,
    descriptor: CSV,
    limits: ProcessingLimits,
) -> ParsedTable:
    if descriptor.delimiter in {"\r", "\n", '"', "\0"}:
        raise SourceReadError(message="Use a CSV delimiter other than a quote or line break.")
    config = {
        "threads": "1",
        "memory_limit": "128MB",
        "temp_directory": "",
        "autoload_known_extensions": "false",
        "autoinstall_known_extensions": "false",
    }
    with StringIO(text) as stream, duckdb.connect(config=config) as connection:
        # DuckDB registers this stream as a private in-memory file. The adapter
        # passes no filesystem path or SQL assembled from the CSV.
        relation = connection.read_csv(
            stream,
            header=False,
            delimiter=descriptor.delimiter,
            all_varchar=True,
            strict_mode=True,
            quotechar='"',
            escapechar='"',
            null_padding=False,
            allow_quoted_nulls=False,
            skiprows=descriptor.header_row - 1,
            max_line_size=limits.max_expanded_bytes,
        )
        width = len(relation.columns)
        if not 1 <= width <= min(limits.max_table_cells, _XLSX_COLUMN_CAP):
            raise ResourceLimitError(message="Keep CSV columns within the configured cell limit.")
        record_limit = limits.max_table_cells // width
        records = relation.limit(record_limit + 1).fetchall()
        if len(records) > record_limit:
            raise ResourceLimitError(message="Keep CSV cells within the configured limit.")
        if not records and descriptor.header_row != 1:
            raise SourceReadError(message="Select an existing CSV header record.")
    return _table(
        name="csv",
        header_row=descriptor.header_row,
        width=width,
        header=records[0] if records else (),
        rows=tuple(enumerate(records[1:], start=descriptor.header_row + 1)),
    )


@final
class DuckDBCSVParser(FormatParser):
    """Parse a configured CSV input using DuckDB."""

    @property
    @override
    def parser_id(self) -> str:
        """Identify the versioned Domain Kernel parser."""
        return "domain-kernel/duckdb-csv-v1"

    @property
    @override
    def parser_version(self) -> str:
        """Identify the installed DuckDB engine."""
        return _version(distribution="duckdb")

    @override
    def parse(
        self, *, content: AcquiredSource, descriptor: FileDescriptor, limits: ProcessingLimits
    ) -> Iterator[ParsedTable]:
        """Yield one rectangular table without altering source cell spellings."""
        if not isinstance(descriptor, CSV):
            raise TypeError("Use the CSV descriptor with the DuckDB parser.")
        duckdb = _load(module="duckdb")
        if not isinstance(duckdb, _DuckDB):
            raise MissingCapabilityError(message=_MISSING_EXTRA)
        _ = _load(module="fsspec")
        if descriptor.header_row > limits.max_table_cells:
            raise ResourceLimitError(
                message="Select a CSV header within the configured cell limit."
            )
        text = _decode_csv(
            raw=_read(content=content, limits=limits), encoding=descriptor.encoding, limits=limits
        )
        try:
            yield _read_csv(duckdb=duckdb, text=text, descriptor=descriptor, limits=limits)
        except duckdb.OutOfMemoryException:
            raise ResourceLimitError(
                message="Keep CSV processing within the engine memory limit."
            ) from None
        except duckdb.Error:
            raise SourceReadError(
                message="Supply a rectangular CSV with matching delimiter, quotes and headers.",
            ) from None


def _column_number(*, letters: str) -> int:
    result = 0
    for letter in letters:
        result = result * 26 + ord(letter) - ord("A") + 1
    return result


def _cell_column(*, element: Element, row: int, previous: int) -> int:
    reference = element.get("r")
    if reference is None:
        return previous + 1
    match = _CELL.fullmatch(reference)
    if match is None or int(match[2]) != row:
        raise ValueError("Use valid and consistent Excel cell coordinates.")
    column = _column_number(letters=match[1])
    if column <= previous:
        raise ValueError("Use ascending Excel column coordinates.")
    return column


def _sheet_extent(*, events: Iterator[tuple[str, Element]], limit: int) -> tuple[bool, int]:
    first = next(events, None)
    is_sheet = first is not None and first[1].tag == f"{_WORKSHEET}worksheet"
    last_row = width = row = column = 0
    for event, element in events:
        if event == "end":
            element.clear()
            continue
        if not is_sheet:
            continue
        if element.tag == f"{_WORKSHEET}row":
            next_row = int(element.get("r", str(row + 1)))
            if next_row <= row:
                raise ValueError("Use ascending Excel row coordinates.")
            if next_row > _XLSX_ROW_CAP:
                raise ResourceLimitError(
                    message="Keep Excel row coordinates within worksheet limits."
                )
            row = next_row
            last_row = max(last_row, row)
            column = 0
        if element.tag == f"{_WORKSHEET}c":
            column = _cell_column(element=element, row=row, previous=column)
            width = max(width, column)
        if width > _XLSX_COLUMN_CAP or max(1, last_row) * max(1, width) > limit:
            raise ResourceLimitError(
                message="Keep Excel cells within the configured worksheet limit."
            )
    return is_sheet, max(1, last_row) * max(1, width) if is_sheet else 0


def _check_workbook(*, raw: bytes, xml: _SafeXML, limits: ProcessingLimits) -> None:
    with ZipFile(BytesIO(raw)) as package:
        entries = package.infolist()
        if sum(entry.file_size for entry in entries) > limits.max_expanded_bytes:
            raise ResourceLimitError(
                message="Keep the expanded workbook within the configured limit."
            )
        if len({entry.filename for entry in entries}) != len(entries):
            raise ValueError("Use unique workbook archive entries.")
        sheets = cells = 0
        for entry in entries:
            if not entry.filename.lower().endswith((".xml", ".rels")):
                continue
            with package.open(entry) as part:
                is_sheet, extent = _sheet_extent(
                    events=xml.iterparse(source=part, events=("start", "end"), forbid_dtd=True),
                    limit=limits.max_table_cells - cells,
                )
            sheets += is_sheet
            cells += extent
            if sheets > limits.max_tables or cells > limits.max_table_cells:
                raise ResourceLimitError(
                    message="Keep workbook sheets and cells within configured limits."
                )


def _excel_value(*, value: object) -> CellValue:
    match value:
        case datetime() if value.utcoffset() is None:
            # Excel timestamps are wall-clock values with no source time zone.
            return value.isoformat()
        case None | bool() | str() | int() | float() | date() | Decimal():
            return value
        case time():
            return value.isoformat()
        case timedelta():
            return str(value)
        case _:
            raise ValueError("Use supported Excel scalar cell values.")


def _excel_table(*, sheet: _Sheet, header_row: int, limits: ProcessingLimits) -> ParsedTable:
    if header_row > min(_XLSX_ROW_CAP, limits.max_table_cells):
        raise ResourceLimitError(message="Select an Excel header within worksheet limits.")
    sheet.reset_dimensions()
    header: Sequence[CellValue] = ()
    rows: list[tuple[int, Sequence[CellValue]]] = []
    width = count = 0
    for number, raw in enumerate(sheet.iter_rows(values_only=True), start=1):
        count = number
        width = max(width, len(raw))
        if number * max(1, width) > limits.max_table_cells:
            raise ResourceLimitError(
                message="Keep Excel cells within the configured worksheet limit."
            )
        if number < header_row:
            continue
        values = tuple(_excel_value(value=value) for value in raw)
        if number == header_row:
            header = values
        elif any(value is not None for value in values):
            rows.append((number, values))
    if header_row > max(1, count):
        raise ValueError("Select an existing Excel header row.")
    return _table(
        name=sheet.title,
        header_row=header_row,
        width=max(1, width),
        header=header,
        rows=rows,
    )


@final
class OpenpyxlExcelParser(FormatParser):
    """Parse a configured Excel workbook using Openpyxl."""

    @property
    @override
    def parser_id(self) -> str:
        """Identify the versioned Domain Kernel parser."""
        return "domain-kernel/openpyxl-excel-v1"

    @property
    @override
    def parser_version(self) -> str:
        """Identify the installed Openpyxl engine."""
        return _version(distribution="openpyxl")

    @override
    def parse(
        self, *, content: AcquiredSource, descriptor: FileDescriptor, limits: ProcessingLimits
    ) -> Iterator[ParsedTable]:
        """Yield bounded worksheets using cached values and exact cell positions."""
        if not isinstance(descriptor, Excel):
            raise TypeError("Use the Excel descriptor with the Openpyxl parser.")
        excel = _load(module="openpyxl")
        xml = _load(module="defusedxml.ElementTree")
        if not isinstance(excel, _Openpyxl) or not isinstance(xml, _SafeXML):
            raise MissingCapabilityError(message=_MISSING_EXTRA)
        raw = _read(content=content, limits=limits)
        try:
            _check_workbook(raw=raw, xml=xml, limits=limits)
            with BytesIO(raw) as stream:
                workbook = excel.load_workbook(
                    filename=stream,
                    read_only=True,
                    data_only=True,
                    keep_links=False,
                )
                try:
                    available = {sheet.title: sheet for sheet in workbook.worksheets}
                    selected = (
                        descriptor.sheets if descriptor.sheets is not None else tuple(available)
                    )
                    if not selected or any(name not in available for name in selected):
                        raise ValueError("Select existing Excel worksheets.")
                    if len(selected) > limits.max_tables:
                        raise ResourceLimitError(
                            message="Keep workbook sheets within the configured limit."
                        )
                    for name in selected:
                        yield _excel_table(
                            sheet=available[name],
                            header_row=descriptor.header_row,
                            limits=limits,
                        )
                finally:
                    workbook.close()
        except (
            BadZipFile,
            KeyError,
            OSError,
            OverflowError,
            RuntimeError,
            SyntaxError,
            ValueError,
        ):
            raise SourceReadError(
                message="Supply a valid Excel workbook and existing sheets."
            ) from None
