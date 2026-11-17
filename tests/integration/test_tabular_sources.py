"""Exercise actual tabular dependencies through verified source acquisition."""

from __future__ import annotations

from importlib import import_module
from io import BytesIO
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from zipfile import ZipFile, ZipInfo

import pytest

from domain_kernel import (
    CSV,
    CellRange,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    DuckDBCSVParser,
    Excel,
    OpenpyxlExcelParser,
    ParsedTable,
    ResourceLimitError,
    SourceReadError,
    SourceRevisionMismatchError,
)
from domain_kernel.configuration import FilesystemReader, InMemoryProcessing

if TYPE_CHECKING:
    from pathlib import Path


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _client(*, directory: Path, processing: InMemoryProcessing | None = None) -> Client:
    return Client(
        config=ClientConfiguration(
            base_dir=directory,
            readers=[FilesystemReader(name="inputs", root="inputs")],
            processing=processing or InMemoryProcessing(),
        ),
        integrations=ClientIntegrations(
            format_parsers={"csv": DuckDBCSVParser(), "excel": OpenpyxlExcelParser()},
        ),
    )


async def test_csv_citations_preserve_quoted_values_and_reopen_exactly(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    path = inputs / "metadata.csv"
    _ = path.write_bytes(
        'id;title;amount\n01;"café; London";2.50\n02;"two\nlines";\n'.encode("latin-1")
    )
    project = await _client(directory=tmp_path).create_project(actor="editor", name="test")
    descriptor = CSV(path="metadata.csv", encoding="latin-1", delimiter=";")
    capture = await project.ingest_source(actor="editor", name="metadata", source=descriptor)
    reopened = await _client(directory=tmp_path).get_project(name="test")
    profile = await reopened.profile_source(actor="reviewer", revision=capture.revision)
    (table,) = profile.tables
    assert table.row_count == len(capture.evidence)
    assert tuple(item.locator for item in capture.evidence) == (
        CellRange(sheet="csv", cells="A2:C2"),
        CellRange(sheet="csv", cells="A3:C3"),
    )
    assert [(column.name, column.inferred_type.value) for column in table.columns] == [
        ("id", "string"),
        ("title", "string"),
        ("amount", "decimal"),
    ]
    assert table.columns[0].identifier_candidate
    assert table.columns[2].nullable
    citation = next(
        evidence
        for evidence in capture.evidence
        if evidence.locator == CellRange(sheet="csv", cells="A3:C3")
    )
    assert citation.source == capture.revision
    resolved = await reopened.get_evidence(evidence=citation)
    assert isinstance(resolved.part, ParsedTable)
    assert resolved.part.rows == (("02", "two\nlines", None),)
    repeated = await reopened.ingest_source_revision(
        actor="editor",
        source_id=capture.source_id,
        source=descriptor,
    )
    assert repeated.evidence == capture.evidence
    _ = path.write_bytes(b"id;title;amount\n03;other;2\n")
    with pytest.raises(SourceRevisionMismatchError):
        _ = await reopened.get_evidence(evidence=citation)


@pytest.mark.parametrize("data", [b"a,b\n1\n", b'a,b\n1,"unfinished\n', b"a\xff,b\n"])
async def test_invalid_csv_rolls_back_its_capture(tmp_path: Path, data: bytes) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "bad.csv").write_bytes(data)
    project = await _client(directory=tmp_path).create_project(actor="editor", name="test")
    with pytest.raises(SourceReadError):
        _ = await project.ingest_source(
            actor="editor",
            name="bad",
            source=CSV(path="bad.csv"),
        )
    assert not (await project.list_sources()).items


class _WritableSheet(Protocol):
    def append(self, values: tuple[str | int, ...], /) -> None: ...


class _WritableWorkbook(Protocol):
    def create_sheet(self, *, title: str) -> _WritableSheet: ...
    def save(self, *, filename: BytesIO) -> None: ...


@runtime_checkable
class _ExcelWriter(Protocol):
    def Workbook(self) -> _WritableWorkbook: ...  # noqa: N802 - Openpyxl constructor.


@pytest.fixture
def workbook_bytes(monkeypatch: pytest.MonkeyPatch) -> bytes:
    with monkeypatch.context() as fixture_environment:
        # Python 3.14 uses SOURCE_DATE_EPOCH for ZIP writes. ZIP timestamps start in 1980.
        fixture_environment.setenv("SOURCE_DATE_EPOCH", "946684800")
        openpyxl: object = import_module(name="openpyxl")
        assert isinstance(openpyxl, _ExcelWriter)
        workbook = openpyxl.Workbook()
        first = workbook.create_sheet(title="Notes")
        first.append(("label", "frequency"))
        first.append(("entry", 4))
        _ = workbook.create_sheet(title="Empty")
        with BytesIO() as output:
            workbook.save(filename=output)
            return output.getvalue()


def _hostile_sheet(*, workbook: bytes, name: str, content: bytes) -> bytes:
    with ZipFile(BytesIO(workbook)) as original, BytesIO() as buffer:
        with ZipFile(buffer, mode="w") as replacement:
            for path in original.namelist():
                replacement.writestr(
                    ZipInfo(filename=path), content if path == name else original.read(path)
                )
        return buffer.getvalue()


async def test_excel_preserves_sheet_coordinates_and_handles_a_blank_sheet(
    tmp_path: Path,
    workbook_bytes: bytes,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "source.xlsx").write_bytes(workbook_bytes)
    project = await _client(directory=tmp_path).create_project(actor="editor", name="test")
    captured = await project.ingest_source(
        actor="editor",
        name="source",
        source=Excel(path="source.xlsx", sheets=["Notes", "Empty"]),
    )
    profile = await project.profile_source(actor="editor", revision=captured.revision)
    assert [(table.name, table.row_count) for table in profile.tables] == [
        ("Notes", 1),
        ("Empty", 0),
    ]
    locator = CellRange(sheet="Notes", cells="A2:B2")
    citation = next(item for item in captured.evidence if item.locator == locator)
    resolved = await project.get_evidence(evidence=citation)
    assert isinstance(resolved.part, ParsedTable)
    assert resolved.part.rows == (("entry", 4),)


async def test_excel_expansion_limit_fails_before_recording_a_source(
    tmp_path: Path,
    workbook_bytes: bytes,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "source.xlsx").write_bytes(workbook_bytes)
    project = await _client(
        directory=tmp_path,
        processing=InMemoryProcessing(max_expanded_bytes=1),
    ).create_project(actor="editor", name="test")
    with pytest.raises(ResourceLimitError):
        _ = await project.ingest_source(
            actor="editor", name="source", source=Excel(path="source.xlsx")
        )
    assert not (await project.list_sources()).items


@pytest.mark.parametrize(
    ("xml", "error"),
    [
        (
            (
                b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                b'<sheetData><row r="1000000"><c r="XFD1000000"><v>1</v></c></row>'
                b"</sheetData></worksheet>"
            ),
            ResourceLimitError,
        ),
        (
            (
                b'<!DOCTYPE worksheet [<!ENTITY huge "expanded">]>'
                b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                b"<sheetData>&huge;</sheetData></worksheet>"
            ),
            SourceReadError,
        ),
    ],
)
async def test_workbook_preflight_rejects_hostile_worksheet(
    tmp_path: Path,
    workbook_bytes: bytes,
    xml: bytes,
    error: type[Exception],
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "bad.xlsx").write_bytes(
        _hostile_sheet(workbook=workbook_bytes, name="xl/worksheets/sheet2.xml", content=xml),
    )
    project = await _client(directory=tmp_path).create_project(actor="editor", name="test")
    with pytest.raises(error):
        _ = await project.ingest_source(
            actor="editor",
            name="bad",
            source=Excel(path="bad.xlsx", sheets=["Notes"]),
        )
    assert not (await project.list_sources()).items


async def test_header_only_csv_has_zero_rows_without_identifier_claims(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "empty.csv").write_bytes(b"title,id\n")
    project = await _client(directory=tmp_path).create_project(actor="editor", name="test")
    result = await project.ingest_source(
        actor="editor",
        name="empty",
        source=CSV(path="empty.csv"),
    )
    profile = await project.profile_source(actor="reviewer", revision=result.revision)
    (table,) = profile.tables
    assert table.row_count == 0
    assert [column.name for column in table.columns] == ["title", "id"]
    assert not any(column.identifier_candidate for column in table.columns)
    assert not result.evidence
