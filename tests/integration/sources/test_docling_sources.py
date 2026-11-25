"""Verify bounded Docling processing through the project API."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Literal, override
from zipfile import ZipFile, ZipInfo

import pytest

from domain_kernel import (
    PDF,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    CoverageStatus,
    CoverageUnit,
    DoclingParser,
    Document,
    DocumentFormat,
    DocumentSpan,
    EvidenceUnavailableError,
    FormatParser,
    LangGraphDiscoveryGateway,
    ModelGateway,
    ModelKind,
    ModelRequest,
    ModelResponse,
    ParsedTable,
    ParsedText,
    ReaderLocation,
    ResourceLimitError,
    RunStatus,
    SourceFolder,
    SourceReadError,
    Word,
)
from domain_kernel._shared.application.inference import InferenceInput
from domain_kernel.configuration import (
    DoclingParser as DoclingConfiguration,
)
from domain_kernel.configuration import (
    FilesystemReader,
    InMemoryProcessing,
    Parsers,
    Retention,
)
from domain_kernel.discovery.application.schema_spans import Inventory, bind_record
from domain_kernel.sources.domain.document_formats import DOCUMENT_EXTENSIONS

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from docling_core.transforms.chunker.base import BaseChunk
    from docling_core.types.doc.document import DoclingDocument

    from domain_kernel import AcquiredSource, FileDescriptor, ProcessingLimits

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_document_registry_matches_pinned_docling_input_catalog() -> None:
    from docling.datamodel.base_models import FormatToExtensions, InputFormat  # noqa: PLC0415

    assert {kind.value for kind in DocumentFormat} == {kind.value for kind in InputFormat}
    for kind, extensions in FormatToExtensions.items():
        assert {extension.casefold() for extension in extensions}.issubset(
            DOCUMENT_EXTENSIONS[DocumentFormat(kind.value)]
        )


@pytest.mark.parametrize(
    ("kind", "filename", "payload", "witness"),
    [
        (
            DocumentFormat.HTML,
            "manual.html",
            b"<html><body><p>Pressure valve</p></body></html>",
            "Pressure valve",
        ),
        (
            DocumentFormat.MD,
            "manual.txt",
            b"# Pressure valve\n\nInspect before opening.",
            "Inspect before opening.",
        ),
        (
            DocumentFormat.EMAIL,
            "manual.eml",
            (
                b"From: editor@example.test\nTo: reader@example.test\nSubject: Work order\n"
                b"MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\n\n"
                b"Inspect the pressure valve.\n"
            ),
            "Inspect the pressure valve.",
        ),
        (
            DocumentFormat.VTT,
            "manual.vtt",
            b"WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nInspect the pressure valve.\n",
            "Inspect the pressure valve.",
        ),
    ],
)
async def test_configured_formats_reopen_native_evidence(
    tmp_path: Path,
    kind: DocumentFormat,
    filename: str,
    payload: bytes,
    witness: str,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / filename).write_bytes(payload)
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
        parsers=Parsers(documents=DoclingConfiguration()),
        retention=Retention(extracted_text=True),
    )
    project = await Client(config=config).create_project(actor="editor", name="example")
    captured = await project.ingest_source(
        actor="editor",
        name="manual",
        source=Document(path=filename, kind=kind),
    )
    (inputs / filename).unlink()
    reopened = await Client(config=config).get_project(name="example")
    profile = await reopened.profile_source(actor="editor", revision=captured.revision)
    assert profile.processed_units > 0
    assert any(unit.status is CoverageStatus.PROCESSED for unit in profile.coverage)
    matches = [
        evidence
        for evidence in captured.evidence
        if witness in (await reopened.get_evidence(evidence=evidence)).excerpt
    ]
    assert matches
    if kind is DocumentFormat.VTT:
        assert any(
            isinstance(item.locator, DocumentSpan)
            and item.locator.section == "media/1.000000/2.500000"
            for item in matches
        )


async def test_docling_json_spans_pin_captured_occurrences_and_table_rows(tmp_path: Path) -> None:
    from docling_core.types.doc.document import DoclingDocument  # noqa: PLC0415
    from docling_core.types.doc.items.table.table_data import (  # noqa: PLC0415
        TableCell,
        TableData,
    )
    from docling_core.types.doc.labels import DocItemLabel  # noqa: PLC0415

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    document = DoclingDocument(name="Maintenance register")
    _ = document.add_heading(text="Inspection register")
    _ = document.add_text(label=DocItemLabel.PARAGRAPH, text="Pressão: verify the valve.")
    cells = [
        TableCell(
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=col,
            end_col_offset_idx=col + 1,
            text=value,
            column_header=row == 0,
        )
        for row, values in enumerate(
            (("Record", "Action"), ("Valve A", "Inspect"), ("Valve B", "Inspect"))
        )
        for col, value in enumerate(values)
    ]
    _ = document.add_table(data=TableData(num_rows=3, num_cols=2, table_cells=cells))
    document.save_as_json(filename=inputs / "inspection.json")
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
        parsers=Parsers(documents=DoclingConfiguration()),
        retention=Retention(extracted_text=True),
    )
    project = await Client(config=config).create_project(actor="editor", name="example")
    captured = await project.ingest_source(
        actor="editor",
        name="register",
        source=Document(path="inspection.json", kind=DocumentFormat.JSON_DOCLING),
    )
    (inputs / "inspection.json").unlink()
    reopened = await Client(config=config).get_project(name="example")
    parts = [await reopened.get_evidence(evidence=evidence) for evidence in captured.evidence]
    corpus = tuple(
        InferenceInput(
            text=part.excerpt,
            evidence=(part.evidence,),
            is_table=isinstance(part.part, ParsedTable),
        )
        for part in parts
    )
    inventory = Inventory.issue(corpus=corpus, selected=tuple(range(len(corpus))))
    paragraph = next(span for span in inventory.spans.values() if "Pressão:" in span.quote)
    assert paragraph.quote == "Pressão: verify the valve."
    assert (paragraph.start, paragraph.end) == (0, len("Pressão: verify the valve."))
    assert isinstance(paragraph.evidence.locator, DocumentSpan)
    assert paragraph.evidence in captured.evidence
    valve = next(span for span in inventory.spans.values() if '"Valve A"' in span.quote)
    actions = [span for span in inventory.spans.values() if '"Inspect"' in span.quote]
    first, second = actions
    assert first.id != second.id
    assert first.start < second.start
    assert first.quote == second.quote
    assert first.quote == parts[first.passage - 1].excerpt[first.start : first.end]
    assert first.evidence == parts[first.passage - 1].evidence
    assert bind_record(anchor=valve, source=valve, target=first) is not None
    assert bind_record(anchor=valve, source=valve, target=second) is None
    assert bind_record(anchor=valve, source=paragraph, target=first) is None
    reduced = inventory.restrict(corpus=corpus, ids={second.id}, byte_limit=512)
    assert set(reduced.spans) == {second.id}
    assert valve.id not in reduced.inputs[0].text


def _client(
    *,
    directory: Path,
    retention: Retention | None = None,
    limits: InMemoryProcessing | None = None,
) -> Client:
    parser = DoclingParser()
    return Client(
        config=ClientConfiguration(
            base_dir=directory,
            readers=[FilesystemReader(name="inputs", root="inputs")],
            processing=limits or InMemoryProcessing(),
            retention=retention or Retention(),
        ),
        integrations=ClientIntegrations(format_parsers={"pdf": parser, "word": parser}),
    )


def _pdf() -> bytes:
    stream = b"BT /F1 12 Tf 30 120 Td (Maintenance procedure) Tj ET"
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 240 180] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    )
    return _pdf_objects(objects=objects)


def _pdf_objects(*, objects: tuple[bytes, ...]) -> bytes:
    content = bytearray(b"%PDF-1.7\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(content)


def _mixed_pdf() -> bytes:
    text = b"BT /F1 12 Tf 20 50 Td (Check the pressure valve.) Tj ET"
    image = b"q 150 0 0 150 0 0 cm /Scan Do Q"
    return _pdf_objects(
        objects=(
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
                b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
            ),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            f"<< /Length {len(text)} >>\nstream\n".encode() + text + b"\nendstream",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
                b"/Resources << /XObject << /Scan 8 0 R >> >> /Contents 7 0 R >>"
            ),
            f"<< /Length {len(image)} >>\nstream\n".encode() + image + b"\nendstream",
            (
                b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray "
                b"/BitsPerComponent 8 /Length 1 >>\nstream\n\x00\nendstream"
            ),
        )
    )


async def test_mixed_pdf_accounts_for_unreadable_pages(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "mixed.pdf").write_bytes(_mixed_pdf())
    project = await _client(directory=tmp_path).create_project(actor="editor", name="example")
    captured = await project.ingest_source(
        actor="editor",
        name="mixed",
        source=PDF(path="mixed.pdf"),
    )
    profile = await project.profile_source(actor="editor", revision=captured.revision)
    assert {
        unit.locator.page for unit in profile.coverage if isinstance(unit.locator, DocumentSpan)
    } == {1, 2}
    scanned_page = 2
    assert any(
        unit.status is CoverageStatus.UNREADABLE
        and isinstance(unit.locator, DocumentSpan)
        and unit.locator.page == scanned_page
        for unit in profile.outstanding_units
    )
    (citation,) = captured.evidence
    assert (await project.get_evidence(evidence=citation)).excerpt == "Check the pressure valve."


@dataclass(frozen=True, kw_only=True)
class _PageCapture(FormatParser):
    version: str
    deferred: bool = False

    @property
    @override
    def parser_id(self) -> str:
        return "test/page-capture"

    @property
    @override
    def parser_version(self) -> str:
        return self.version

    @override
    def parse(
        self, *, content: AcquiredSource, descriptor: FileDescriptor, limits: ProcessingLimits
    ) -> Iterator[ParsedText | CoverageUnit]:
        page = "First item. Second item."
        yield ParsedText(locator=DocumentSpan(page=1, start=0, end=len(page)), text=page)
        if self.deferred:
            yield CoverageUnit(
                locator=DocumentSpan(page=2, start=0, end=1), status=CoverageStatus.DEFERRED
            )
            return
        yield ParsedText(
            locator=DocumentSpan(
                page=1, start=0, end=11, section="docling-chunk/0/pages/1/items/ref"
            ),
            text="First item.",
        )
        yield ParsedText(locator=DocumentSpan(page=2, start=0, end=11), text="Third item.")


class _ObserveDiscovery(ModelGateway):
    supports_schema_discovery: bool = True

    def __init__(self) -> None:
        self.requests: list[tuple[str, ...]] = []

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        self.requests.append(tuple(item.text.partition("] ")[2] for item in request.inputs))
        output = (
            '{"concepts":[],"relationships":[],"questions":[],"unresolved_facets":[]}'
            if request.provider_stage == "schema-compact-draft"
            else (
                '{"upsert":{"concepts":[],"relationships":[],"questions":[]},'
                '"drop":[],"label_edits":[],"label_flags":[],"checks":[{"facet_id":1,'
                '"example":null,"contrast":null,"status":"insufficient","concepts":[],"links":[],'
                '"witnesses":[],"reason":"No reusable item definition was sourced."}]}'
            )
        )
        return ModelResponse(output_json=output, model_id="test/observe")


async def test_discovery_resumes_deferred_capture_and_keeps_full_pages(tmp_path: Path) -> None:
    pytest.importorskip("langgraph.graph")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "pages.pdf").write_bytes(_mixed_pdf())
    witness = _ObserveDiscovery()
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
        retention=Retention(extracted_text=True),
        model_gateway=LangGraphDiscoveryGateway(
            evidence_bound=False, gateway=witness, profile="test", directory=tmp_path / "workflow"
        ),
    )
    initial = ClientIntegrations(format_parsers={"pdf": _PageCapture(version="1", deferred=True)})
    project = await Client(config=config, integrations=initial).create_project(
        actor="editor", name="example"
    )
    descriptor = PDF(path="pages.pdf")
    capture = await project.ingest_source(actor="editor", name="pages", source=descriptor)
    model = await project.create_model(
        actor="editor", name="items", kind=ModelKind.OBSERVED, description="Review the items."
    )
    deferred = await model.discover(sources=[capture.revision], actor="editor")
    assert deferred.status is RunStatus.FAILED
    assert "deferred units" in deferred.failures[0].message
    assert not witness.requests

    complete = ClientIntegrations(format_parsers={"pdf": _PageCapture(version="1")})
    reopened = await Client(config=config, integrations=complete).get_project(name="example")
    updated = await reopened.ingest_source_revision(
        actor="editor", source_id=capture.source_id, source=descriptor
    )
    assert updated.revision == capture.revision
    assert updated.processing_fingerprint != capture.processing_fingerprint
    assert (await reopened.get_evidence(evidence=capture.evidence[0])).excerpt == (
        "First item. Second item."
    )
    old_profile = await reopened.profile_source(
        actor="editor",
        revision=capture.revision,
        processing_fingerprint=capture.processing_fingerprint,
    )
    assert old_profile.outstanding_units[0].status is CoverageStatus.DEFERRED
    new_profile = await reopened.profile_source(actor="editor", revision=updated.revision)
    assert not new_profile.outstanding_units
    current = await reopened.get_model(name="items")
    resumed = await current.resume_discovery(actor="editor", run_id=deferred.id)
    assert resumed.id == deferred.id
    assert resumed.status is RunStatus.READY_TO_PREPARE, resumed.failures
    assert witness.requests[0] == ("First item. Second item.", "First item.", "Third item.")


async def test_folder_uses_docling_for_slides_and_requires_xml_selection(tmp_path: Path) -> None:
    from pptx.api import Presentation  # noqa: PLC0415 - Optional Docling dependency.
    from pptx.util import Inches  # noqa: PLC0415 - Test fixture geometry.

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    presentation = Presentation()
    slide = presentation.slides.add_slide(slide_layout=presentation.slide_layouts[6])
    box = slide.shapes.add_textbox(
        left=Inches(1),
        top=Inches(1),
        width=Inches(6),
        height=Inches(1),
    )
    box.text = "Check the pressure valve."
    _ = presentation.slides.add_slide(slide_layout=presentation.slide_layouts[6])
    presentation.save(file=str(inputs / "slides.PPTX"))
    _ = (inputs / "unknown.xml").write_text("<unknown />", encoding="utf-8")
    client = Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            readers=[FilesystemReader(name="inputs", root="inputs")],
            parsers=Parsers(documents=DoclingConfiguration()),
        )
    )
    project = await client.create_project(actor="editor", name="test")
    result = await project.ingest_sources(
        actor="editor",
        sources=[SourceFolder(location=ReaderLocation(reader="inputs", path="."))],
    )
    (success,) = result.successes
    (failure,) = result.failures
    assert "explicitly" in failure.message
    profile = await project.profile_source(
        actor="editor", revision=success.ingested_source.revision
    )
    assert (
        CoverageUnit(locator=DocumentSpan(page=2, start=0, end=1), status=CoverageStatus.EMPTY)
        in profile.coverage
    )
    (citation,) = (
        evidence
        for evidence in success.ingested_source.evidence
        if isinstance(evidence.locator, DocumentSpan)
        and evidence.locator.page == 1
        and evidence.locator.section is None
    )
    assert (await project.get_evidence(evidence=citation)).excerpt == "Check the pressure valve."


def _docx() -> bytes:
    prefix = "http://schemas.openxmlformats.org"
    heading = (
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Inspection</w:t></w:r></w:p>'
    )
    main = (
        f'<w:document xmlns:w="{prefix}/wordprocessingml/2006/main"><w:body>'
        f"{heading}{heading}"
        '<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="1440"/><w:gridCol w:w="1440"/></w:tblGrid>'
        "<w:tr><w:tc><w:p><w:r><w:t>Part</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>Check</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>Valve</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>Pressure</w:t></w:r></w:p></w:tc></w:tr>"
        "</w:tbl><w:sectPr/></w:body></w:document>"
    )
    contents = (
        f'<Types xmlns="{prefix}/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )
    relations = (
        f'<Relationships xmlns="{prefix}/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{prefix}/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    document_relations = (
        f'<Relationships xmlns="{prefix}/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{prefix}/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>'
    )
    styles = (
        f'<w:styles xmlns:w="{prefix}/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
        '<w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style></w:styles>'
    )
    with BytesIO() as output:
        with ZipFile(output, mode="w") as archive:
            for name, data in (
                ("[Content_Types].xml", contents),
                ("_rels/.rels", relations),
                ("word/document.xml", main),
                ("word/_rels/document.xml.rels", document_relations),
                ("word/styles.xml", styles),
            ):
                archive.writestr(ZipInfo(filename=name), data)
        return output.getvalue()


@pytest.mark.parametrize(
    "retention",
    [
        Retention(),
        Retention(extracted_text=True),
        Retention(evidence_excerpts=True),
        Retention(originals=True),
    ],
    ids=["upstream", "normalized", "excerpt", "original"],
)
async def test_pdf_citation_reopens_the_exact_page_or_retained_capture(
    tmp_path: Path,
    retention: Retention,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    path = inputs / "procedures.pdf"
    _ = path.write_bytes(_pdf())
    project = await _client(directory=tmp_path, retention=retention).create_project(
        actor="editor", name="test"
    )
    captured = await project.ingest_source(
        actor="editor",
        name="procedures",
        source=PDF(path="procedures.pdf", pages=[1]),
    )
    (evidence,) = captured.evidence
    assert evidence.source == captured.revision
    assert evidence.locator == DocumentSpan(page=1, start=0, end=len("Maintenance procedure"))
    reopened = await _client(directory=tmp_path).get_project(name="test")
    resolved = await reopened.get_evidence(evidence=evidence)
    assert resolved.excerpt == "Maintenance procedure"
    profile = await reopened.profile_source(actor="reviewer", revision=captured.revision)
    assert profile.page_count == 1
    path.unlink()
    if retention != Retention():
        assert await reopened.get_evidence(evidence=evidence) == resolved
    else:
        with pytest.raises(EvidenceUnavailableError):
            _ = await reopened.get_evidence(evidence=evidence)


async def test_word_structure_cites_repeated_text_and_table(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "procedure.docx").write_bytes(_docx())
    project = await _client(directory=tmp_path).create_project(actor="editor", name="test")
    captured = await project.ingest_source(
        actor="editor",
        name="procedure",
        source=Word(path="procedure.docx"),
    )
    resolved = [await project.get_evidence(evidence=item) for item in captured.evidence]
    repetitions = [item for item in resolved if item.excerpt == "Inspection"]
    assert len(repetitions) == len({item.evidence.locator for item in repetitions}) == 2  # noqa: PLR2004
    assert all(
        isinstance(item.evidence.locator, DocumentSpan)
        and item.evidence.locator.section == "Inspection"
        for item in repetitions
    )
    (table,) = (item.part for item in resolved if isinstance(item.part, ParsedTable))
    assert ("Valve", "Pressure") in table.rows


async def test_damaged_pdf_does_not_record_a_partial_source(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "damaged.pdf").write_bytes(b"%PDF-1.7\ninvalid content")
    project = await _client(directory=tmp_path).create_project(actor="editor", name="test")
    with pytest.raises(SourceReadError):
        _ = await project.ingest_source(
            actor="editor",
            name="damaged",
            source=PDF(path="damaged.pdf"),
        )
    assert not (await project.list_sources()).items


async def test_document_selection_enforces_the_configured_page_limit(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _ = (inputs / "procedures.pdf").write_bytes(_pdf())
    project = await _client(
        directory=tmp_path, limits=InMemoryProcessing(max_pages=1)
    ).create_project(
        actor="editor",
        name="test",
    )
    with pytest.raises(ResourceLimitError):
        _ = await project.ingest_source(
            actor="editor",
            name="procedures",
            source=PDF(path="procedures.pdf", pages=[2]),
        )
    assert not (await project.list_sources()).items


@pytest.mark.parametrize("mode", ["hybrid", "hierarchical", "custom"])
async def test_chunk_parser_preserves_physical_page_evidence(
    tmp_path: Path, mode: Literal["hybrid", "hierarchical", "custom"]
) -> None:
    pytest.importorskip("docling.chunking")
    data = tmp_path / "inputs"
    data.mkdir()
    _ = (data / "policy.pdf").write_bytes(_pdf())
    if mode == "custom":
        from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker  # noqa: PLC0415 -- optional integration

        chunker = HierarchicalChunker()
        with pytest.raises(ValueError, match="fingerprint"):
            _ = DoclingParser.for_discovery(chunking=chunker)
        parser = DoclingParser.for_discovery(chunking=chunker, chunker_fingerprint="host-v1")
        assert "host-v1" in parser.parser_version
    else:
        parser = DoclingParser.for_discovery(chunking=mode)
    client = Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            readers=[FilesystemReader(name="inputs", root="inputs")],
            retention=Retention(extracted_text=True),
        ),
        integrations=ClientIntegrations(format_parsers={"pdf": parser}),
    )
    project = await client.create_project(name="policy", actor="reader")
    source = await project.ingest_source(
        name="policy", actor="reader", source=PDF(path="policy.pdf")
    )
    excerpts = [
        (item.locator, (await project.get_evidence(evidence=item)).excerpt)
        for item in source.evidence
    ]
    assert any(
        isinstance(loc, DocumentSpan) and loc.page == 1 and loc.section is None
        for loc, _ in excerpts
    )
    assert any(
        isinstance(loc, DocumentSpan)
        and (loc.section or "").startswith("docling-chunk/")
        and "Maintenance procedure" in text
        for loc, text in excerpts
    )


async def test_selected_pdf_retains_only_chunks_with_in_scope_page_provenance(
    tmp_path: Path,
) -> None:
    pytest.importorskip("docling.chunking")
    from docling_core.transforms.chunker.doc_chunk import DocChunk  # noqa: PLC0415 -- Optional Docling integration.
    from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker  # noqa: PLC0415

    injected: list[str] = []

    class HostChunker(HierarchicalChunker):
        @override
        def chunk(self, dl_doc: DoclingDocument, **kwargs: object) -> Iterator[BaseChunk]:
            for chunk in super().chunk(dl_doc=dl_doc, **kwargs):
                assert isinstance(chunk, DocChunk)
                item = chunk.meta.doc_items[0]
                provenance = item.prov[0]
                for text, pages in (
                    ("missing", []),
                    ("out of selection", [provenance.model_copy(update={"page_no": 2})]),
                ):
                    injected.append(text)
                    yield DocChunk(
                        text=text,
                        meta=chunk.meta.model_copy(
                            update={"doc_items": [item.model_copy(update={"prov": pages})]}
                        ),
                    )
                yield chunk

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    path = inputs / "manual.pdf"
    _ = path.write_bytes(_mixed_pdf())
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
        retention=Retention(extracted_text=True),
    )
    parser = DoclingParser.for_discovery(
        chunking=HostChunker(), chunker_fingerprint="missing-page-fixture-v1"
    )
    project = await Client(
        config=config, integrations=ClientIntegrations(format_parsers={"pdf": parser})
    ).create_project(name="maintenance", actor="reader")
    captured = await project.ingest_source(
        name="manual", actor="reader", source=PDF(path="manual.pdf", pages=[1])
    )
    assert injected == ["missing", "out of selection"]
    (chunk,) = (
        item
        for item in captured.evidence
        if isinstance(item.locator, DocumentSpan)
        and (item.locator.section or "").startswith("docling-chunk/")
    )
    assert isinstance(chunk.locator, DocumentSpan)
    assert chunk.locator.page == 1
    assert chunk.source == captured.revision
    path.unlink()
    reopened = await Client(config=config).get_project(name="maintenance")
    assert (await reopened.get_evidence(evidence=chunk)).excerpt == "Check the pressure valve."
