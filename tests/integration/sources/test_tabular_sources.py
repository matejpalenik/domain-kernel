"""Exercise actual tabular dependencies through verified source acquisition."""

from __future__ import annotations

from importlib import import_module
from io import BytesIO
from typing import TYPE_CHECKING, override
from zipfile import ZipFile, ZipInfo

import pytest

from domain_kernel import (
    CSV,
    AcquiredSource,
    CellRange,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    CoverageUnit,
    DoclingParser,
    Excel,
    ModelGateway,
    ModelKind,
    ModelRequest,
    ModelResponse,
    ParsedTable,
    ParsedText,
    ProcessingLimits,
    ResourceLimitError,
    SourceReadError,
    SourceRevisionMismatchError,
)
from domain_kernel.configuration import (
    DoclingParser as DoclingConfiguration,
)
from domain_kernel.configuration import (
    FilesystemReader,
    InMemoryProcessing,
    Parsers,
    Retention,
)
from tests.support.xlsx import ExcelWriter

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from domain_kernel import FileDescriptor


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _client(*, directory: Path, processing: InMemoryProcessing | None = None) -> Client:
    parser = DoclingParser()
    return Client(
        config=ClientConfiguration(
            base_dir=directory,
            readers=[FilesystemReader(name="inputs", root="inputs")],
            processing=processing or InMemoryProcessing(),
        ),
        integrations=ClientIntegrations(
            format_parsers={"csv": parser, "excel": parser},
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


async def test_docling_csv_distinguishes_quoted_empty_values_from_nulls(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "metadata.csv").write_text(
        'value|missing|literal\n""||"a""b"\n', encoding="utf-8"
    )
    project = await _client(directory=tmp_path).create_project(actor="editor", name="test")
    captured = await project.ingest_source(
        actor="editor",
        name="metadata",
        source=CSV(path="metadata.csv", delimiter="|"),
    )
    (citation,) = captured.evidence
    item = await project.get_evidence(evidence=citation)
    assert isinstance(item.part, ParsedTable)
    assert item.part.rows == (("", None, 'a"b'),)


@pytest.fixture
def workbook_bytes(monkeypatch: pytest.MonkeyPatch) -> bytes:
    with monkeypatch.context() as fixture_environment:
        # Python 3.14 uses SOURCE_DATE_EPOCH for ZIP writes. ZIP timestamps start in 1980.
        fixture_environment.setenv("SOURCE_DATE_EPOCH", "946684800")
        openpyxl: object = import_module(name="openpyxl")
        assert isinstance(openpyxl, ExcelWriter)
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


async def test_configured_docling_covers_rows_beyond_the_profiling_sample(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    row_count = 21
    table = "name;code\n" + "".join(f"entry-{row};00{row}\n" for row in range(1, row_count + 1))
    _ = (inputs / "inventory.csv").write_text(table, encoding="utf-8")
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
        parsers=Parsers(documents=DoclingConfiguration()),
        retention=Retention(extracted_text=True),
    )
    project = await Client(config=config).create_project(actor="editor", name="example")
    captured = await project.ingest_source(
        actor="editor", name="inventory", source=CSV(path="inventory.csv", delimiter=";")
    )
    assert len(captured.evidence) == row_count
    citation = captured.evidence[-1]
    assert citation.locator == CellRange(sheet="csv", cells="A22:B22")
    assert "docling" in citation.processing.parser_id
    (inputs / "inventory.csv").unlink()
    reopened = await Client(config=config).get_project(name="example")
    profile = await reopened.profile_source(actor="editor", revision=captured.revision)
    assert profile.processed_units == profile.accounted_units == row_count
    assert not profile.outstanding_units
    resolved = await reopened.get_evidence(evidence=citation)
    assert isinstance(resolved.part, ParsedTable)
    assert resolved.part.rows == (("entry-21", "0021"),)


class _ObserveExtraction(ModelGateway):
    def __init__(self) -> None:
        self.inputs: list[str] = []

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        self.inputs.extend(part.text for part in request.inputs)
        return ModelResponse(
            output_json='{"concepts":[],"relationships":[]}', model_id="test/observe"
        )


async def test_excel_discovery_reparses_once_and_reads_the_last_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openpyxl: object = import_module(name="openpyxl")
    assert isinstance(openpyxl, ExcelWriter)
    workbook = openpyxl.Workbook()
    sheet = workbook.create_sheet(title="Orders")
    sheet.append(("label", "amount"))
    row_count = 24
    for row in range(row_count):
        sheet.append((f"record-{row}", row))
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    with BytesIO() as buffer:
        workbook.save(filename=buffer)
        _ = (inputs / "orders.xlsx").write_bytes(buffer.getvalue())
    adapter_parse = DoclingParser.parse
    conversions = 0

    def observed_parse(
        self: DoclingParser,
        *,
        content: AcquiredSource,
        descriptor: FileDescriptor,
        limits: ProcessingLimits,
    ) -> Iterator[ParsedText | ParsedTable | CoverageUnit]:
        nonlocal conversions
        conversions += 1
        return adapter_parse(self, content=content, descriptor=descriptor, limits=limits)

    monkeypatch.setattr(DoclingParser, "parse", observed_parse)
    gateway = _ObserveExtraction()
    client = Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            readers=[FilesystemReader(name="inputs", root="inputs")],
            parsers=Parsers(documents=DoclingConfiguration()),
            model_gateway=gateway,
        )
    )
    project = await client.create_project(actor="editor", name="example")
    captured = await project.ingest_source(
        actor="editor",
        name="orders",
        source=Excel(path="orders.xlsx", sheets=["Orders"]),
    )
    model = await project.create_model(
        actor="editor",
        name="orders",
        kind=ModelKind.OBSERVED,
        description="Review orders.",
    )
    draft = await model.extract_proposals(
        source_revisions=[captured.revision], actor="editor", idempotency_key="all-rows"
    )
    assert not draft.proposals
    assert "record-23" in gateway.inputs[-1]
    assert len(gateway.inputs) == row_count
    assert conversions == 2  # noqa: PLR2004 - One ingestion conversion and one discovery conversion.


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
