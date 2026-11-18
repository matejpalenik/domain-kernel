"""Verify bounded Docling processing through the project API."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Literal
from zipfile import ZipFile, ZipInfo

import pytest

from domain_kernel import (
    PDF,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    DoclingParser,
    DocumentSpan,
    EvidenceUnavailableError,
    ParsedTable,
    ResourceLimitError,
    SourceReadError,
    Word,
)
from domain_kernel.configuration import FilesystemReader, InMemoryProcessing, Retention

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


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
