"""Tabular projection of Docling conversions with original row coordinates."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from importlib import import_module
from io import BytesIO
from typing import TYPE_CHECKING, Protocol, override, runtime_checkable
from zipfile import ZipFile

from domain_kernel.shared.errors.missing_capability_error import MissingCapabilityError
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.errors.source_read_error import SourceReadError
from domain_kernel.sources.domain.coverage import CoverageStatus, CoverageUnit
from domain_kernel.sources.domain.parsed import CellRange, CellValue, ParsedTable

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from typing import IO
    from xml.etree.ElementTree import Element

    from docling_core.types.doc.document import DoclingDocument

    from domain_kernel.sources.application.contracts import CSV
    from domain_kernel.sources.domain.models import ProcessingLimits

_XLSX_ROW_CAP = 1_048_576
_XLSX_COLUMN_CAP = 16_384
_CELL = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")
_WORKSHEET = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_QUOTED_EMPTY = "\0"


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


def check_workbook(*, raw: bytes, limits: ProcessingLimits) -> None:
    """Preflight the Excel container before Docling opens it."""
    xml = import_module(name="defusedxml.ElementTree")
    if not isinstance(xml, _SafeXML):
        raise MissingCapabilityError(message="Install the Domain Kernel documents extra.")
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


class _Sheet(Protocol):
    @property
    def title(self) -> str: ...
    def iter_rows(self, *, values_only: bool) -> Iterator[tuple[object, ...]]: ...


def excel_options(
    *,
    sheets: Sequence[str] | None,
    header_row: int,
    limits: ProcessingLimits,
    tables: list[ParsedTable],
) -> object:
    """Project typed values from the same workbook Docling has already opened."""
    from docling.backend.msexcel_backend import MsExcelDocumentBackend  # noqa: PLC0415
    from docling.datamodel.backend_options import MsExcelBackendOptions  # noqa: PLC0415
    from docling.document_converter import ExcelFormatOption  # noqa: PLC0415

    class TypedExcelBackend(MsExcelDocumentBackend):
        @override
        def convert(self) -> DoclingDocument:
            document = super().convert()
            if self.workbook is None:
                raise SourceReadError(message="Supply a readable Excel workbook.")
            available = {sheet.title: sheet for sheet in self.workbook.worksheets}
            selected = tuple(available) if sheets is None else sheets
            if not selected or any(name not in available for name in selected):
                raise SourceReadError(message="Select existing Excel worksheets.")
            if len(selected) > limits.max_tables:
                raise ResourceLimitError(
                    message="Keep workbook sheets within the configured limit."
                )
            tables.extend(
                _excel_table(sheet=available[name], header_row=header_row, limits=limits)
                for name in selected
            )
            return document

    return ExcelFormatOption(
        backend=TypedExcelBackend,
        backend_options=MsExcelBackendOptions.model_validate(
            {
                "sheet_names": list(sheets) if sheets is not None else None,
                "max_total_bytes": limits.max_expanded_bytes,
                "max_file_bytes": limits.max_expanded_bytes,
                "parse_charts": False,
            }
        ),
    )


def csv_payload(*, raw: bytes, descriptor: CSV, limits: ProcessingLimits) -> bytes:
    """Pass the requested dialect using Docling's separator directive."""
    if descriptor.delimiter not in ",;\t|:":
        raise SourceReadError(
            message="Use a Docling CSV separator: comma, semicolon, tab, pipe, or colon."
        )
    try:
        decoded = raw.decode(encoding=descriptor.encoding).removeprefix("\ufeff")
    except (LookupError, UnicodeError):
        raise SourceReadError(message="Choose the CSV's declared text encoding.") from None
    if "\0" in decoded:
        raise SourceReadError(message="Supply CSV text without NUL characters.")
    if len(decoded.encode()) > limits.max_expanded_bytes:
        raise ResourceLimitError(message="Keep decoded CSV bytes within the configured limit.")
    first_line, _, rest = decoded.partition("\n")
    if first_line.rstrip("\r") == f"sep={descriptor.delimiter}":
        decoded = rest
    if '""' in decoded:
        # Protect quoted empty values before Docling collapses them with null fields.
        separator = re.escape(descriptor.delimiter)
        quoted_field = re.compile(rf'(?<![^\r\n{separator}])"(?:[^"]|"")*"(?=$|[\r\n{separator}])')
        decoded = quoted_field.sub(
            lambda match: f'"{_QUOTED_EMPTY}"' if match[0] == '""' else match[0], decoded
        )
    payload = f"sep={descriptor.delimiter}\n{decoded}".encode()
    if len(payload) > limits.max_expanded_bytes:
        raise ResourceLimitError(message="Keep decoded CSV bytes within the configured limit.")
    return payload


def csv_table(
    *,
    rows: Sequence[Sequence[str]],
    header_row: int,
    limits: ProcessingLimits,
) -> ParsedTable:
    """Project the Docling CSV table with declared header and logical row numbers."""
    selected = rows[header_row - 1 :]
    if not selected and header_row != 1:
        raise SourceReadError(message="Select an existing CSV header record.")
    header = selected[0] if selected else ()
    width = len(header) or 1
    if width > _XLSX_COLUMN_CAP or width * max(1, len(selected)) > limits.max_table_cells:
        raise ResourceLimitError(message="Keep CSV cells within the configured limit.")
    if any(len(row) != width for row in selected):
        raise SourceReadError(message="Use a consistent number of fields in each CSV record.")
    return _table(
        name="csv",
        header_row=header_row,
        width=width,
        header=tuple("" if value == _QUOTED_EMPTY else value for value in header),
        rows=tuple(
            (index, tuple("" if value == _QUOTED_EMPTY else value or None for value in row))
            for index, row in enumerate(selected[1:], start=header_row + 1)
        ),
    )


def csv_options(
    *,
    descriptor: CSV,
    limits: ProcessingLimits,
    tables: list[ParsedTable],
) -> object:
    """Validate Docling's logical rows before projecting them into the SDK table."""
    from docling.backend.csv_backend import CsvDocumentBackend  # noqa: PLC0415
    from docling.datamodel.backend_options import CsvBackendOptions  # noqa: PLC0415
    from docling.document_converter import CsvFormatOption  # noqa: PLC0415

    class StrictCsvBackend(CsvDocumentBackend):
        @override
        def convert(self) -> DoclingDocument:
            document = super().convert()
            tables.append(
                csv_table(
                    rows=self.csv_data,
                    header_row=descriptor.header_row,
                    limits=limits,
                )
            )
            return document

    return CsvFormatOption(
        backend=StrictCsvBackend,
        backend_options=CsvBackendOptions.model_validate({"encoding": "utf-8"}),
    )


def empty_table_unit(*, table: ParsedTable) -> Iterator[CoverageUnit]:
    """Account for a selected worksheet or CSV header with no data rows."""
    if not table.rows:
        yield CoverageUnit(locator=table.locator, status=CoverageStatus.EMPTY)
