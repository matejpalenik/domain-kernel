"""Gold source-to-review checks for a scanned page and a late workbook row."""

from __future__ import annotations

import json
import os
import zlib
from importlib import import_module
from io import BytesIO
from typing import TYPE_CHECKING, override

import pytest
from pydantic import TypeAdapter

from domain_kernel import (
    PDF,
    CellRange,
    Client,
    ClientConfiguration,
    DocumentSpan,
    Excel,
    LangGraphDiscoveryGateway,
    ModelGateway,
    ModelKind,
    ModelRequest,
    ModelResponse,
    ParsedTable,
    RelationshipDefinition,
)
from domain_kernel.configuration import DoclingParser, FilesystemReader, Parsers, Retention
from domain_kernel.shared.application.inference import TruncatedResponse, TruncatedResponseError
from tests.support.xlsx import ExcelWriter

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
_ACTOR = "Panel"
_TARGET = "Motor"
_QUALIFIER = "if enabled"
_ASSERTION = "Panel powers Motor if enabled."


def _stream(content: bytes, *, extra: bytes = b"") -> bytes:
    return (
        f"<< /Length {len(content)} ".encode() + extra + b" >>\nstream\n" + content + b"\nendstream"
    )


def _mixed_pdf() -> bytes:
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415 - Docling image fixture.

    scan = Image.new("L", (1450, 800), color="white")
    font = ImageFont.load_default(size=52)
    ImageDraw.Draw(scan).text(xy=(66, 300), text=_ASSERTION, fill="black", font=font)
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 500 320] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        _stream(b"BT /F1 16 Tf 27 200 Td (Read the maintenance log.) Tj ET"),
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 500 320] "
            b"/Resources << /XObject << /Scan 8 0 R >> >> /Contents 7 0 R >>"
        ),
        _stream(b"q 500 0 0 276 0 0 cm /Scan Do Q"),
        _stream(
            zlib.compress(scan.tobytes()),
            extra=(
                b"/Type /XObject /Subtype /Image /Width 1450 /Height 800 /ColorSpace /DeviceGray "
                b"/BitsPerComponent 8 /Filter /FlateDecode"
            ),
        ),
    )
    content = bytearray(b"%PDF-1.7\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(content)


def _workbook(path: Path) -> None:
    excel: object = import_module("openpyxl")
    assert isinstance(excel, ExcelWriter)
    workbook = excel.Workbook()
    sheet = workbook.create_sheet(title="Orders")
    sheet.append(("Device", "Action", "Load", "Rule", "Count"))
    for index in range(21):
        sheet.append((f"OtherPanel{index}", "checks", "Diverter", "when free", index))
    sheet.append((_ACTOR, "powers", _TARGET, _QUALIFIER, 7))
    with BytesIO() as buffer:
        workbook.save(filename=buffer)
        _ = path.write_bytes(buffer.getvalue())


def _answer(**content: object) -> ModelResponse:
    return ModelResponse(output_json=json.dumps(content), model_id="fixture/documents")


def _anchor(citation: int, quote: str) -> dict[str, object]:
    return {"citation": citation, "quote": quote}


def _cutoff() -> TruncatedResponseError:
    return TruncatedResponseError(
        response=TruncatedResponse(
            fragment='{"claims":[',
            model_id="fixture/documents",
            provider_request_id=None,
            provider_endpoint="https://example.test",
            input_tokens=200,
            output_tokens=32_768,
        )
    )


class _DocumentFixture(ModelGateway):
    def __init__(self, *, table: bool) -> None:
        self.table: bool = table
        self.checked_context: bool = False

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        has_fact = any(_TARGET in item.text and _QUALIFIER in item.text for item in request.inputs)
        if "omission_window" in context:
            if self.table:
                assert "Count" in str(context["column_headers"])
                raise _cutoff()
            return _answer(claims=[])
        if "prior_claims" in context:
            if has_fact:
                raise _cutoff()
            return _answer(claims=[])
        if "held_claims" in context:
            if self.table:
                assert all("OtherPanel" not in item.text for item in request.inputs)
                assert any(
                    "Device" in item.text and "Count" in item.text for item in request.inputs
                )
            assert any(_ACTOR in item.text and _TARGET in item.text for item in request.inputs)
            self.checked_context = True
            return _answer(
                choices=[{"index": 0, "source": None, "target": {"key": None, "quote": _TARGET}}]
            )
        packet = context.get("claims", context.get("edges"))
        if packet is not None:
            rows = TypeAdapter(list[object]).validate_python(packet)
            return _answer(
                verdicts=[
                    {"index": i, "status": "supported", "reason": "The source supports the roles."}
                    for i, _ in enumerate(rows)
                ]
            )
        if not has_fact:
            return _answer(claims=[])
        index = next(
            i
            for i, item in enumerate(request.inputs, 1)
            if _TARGET in item.text and _QUALIFIER in item.text
        )
        quote = "Motor" if self.table else "powers Motor if enabled"
        return _answer(
            claims=[
                {
                    "kind": "concept",
                    "name": "panel",
                    "title": _ACTOR,
                    "meaning": "The control panel.",
                    "source": None,
                    "target": None,
                    "evidence": [_anchor(index, _ACTOR)],
                    "conditions": [],
                    "exceptions": [],
                },
                {
                    "kind": "relationship",
                    "name": "powers",
                    "title": "Powers",
                    "meaning": _ASSERTION,
                    "source": "panel",
                    "target": "motor",
                    "evidence": [_anchor(index, quote)],
                    "conditions": [{"text": _QUALIFIER, "evidence": [_anchor(index, _QUALIFIER)]}],
                    "exceptions": [],
                },
            ]
        )


@pytest.mark.parametrize("table", [False, True], ids=["scanned-pdf", "late-xlsx-row"])
@pytest.mark.filterwarnings(
    "ignore:This field is deprecated.*generate_page_images:DeprecationWarning"
)
@pytest.mark.filterwarnings("ignore:^deprecated$:DeprecationWarning:docling")
@pytest.mark.filterwarnings(
    "ignore:^Using padding='same' with even kernel lengths:UserWarning:torch"
)
async def test_docling_windows_reopen_gold_endpoints(tmp_path: Path, *, table: bool) -> None:
    artifacts = os.environ.get("DK_TEST_DOCLING_ARTIFACTS")
    if not table and artifacts is None:
        pytest.skip("Provide pinned local Docling layout and OCR assets.")
    source: PDF | Excel
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    if table:
        _workbook(inputs / "orders.xlsx")
        source = Excel(path="orders.xlsx", sheets=["Orders"])
    else:
        _ = (inputs / "manual.pdf").write_bytes(_mixed_pdf())
        source = PDF(path="manual.pdf")
    provider = _DocumentFixture(table=table)
    graph = LangGraphDiscoveryGateway(
        gateway=provider,
        directory=tmp_path / "audit",
        profile="fixture/document-windows",
        proposal_batching=True,
        resumable_omissions=True,
        held_endpoint_repair=True,
    )
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
        parsers=Parsers(
            documents=DoclingParser(artifacts_path=None if table else artifacts, ocr=not table)
        ),
        retention=Retention(extracted_text=True),
        model_gateway=graph,
    )
    project = await Client(config=config).create_project(actor="reviewer", name="test")
    captured = await project.ingest_source(actor="reviewer", name="input", source=source)
    model = await project.create_model(
        actor="reviewer",
        name="maintenance",
        kind=ModelKind.OBSERVED,
        description="Review the direction of equipment relationships.",
    )
    draft = await model.extract_proposals(actor="reviewer", source_revisions=[captured.revision])
    alignment = await model.propose_alignment(actor="reviewer", discovery_id=draft.id)
    assert provider.checked_context
    (manifest,) = draft.coverage
    expected = CellRange(sheet="Orders", cells="A23:E23") if table else None
    if table:
        (window,) = manifest.deferred
        assert window.evidence.locator == expected
    else:
        assert not manifest.deferred
        pages = {
            w.evidence.locator.page
            for w in manifest.completed
            if isinstance(w.evidence.locator, DocumentSpan)
        }
        assert pages == {1, 2}
    cases = (await model.list_review_cases(reconciliation_id=alignment.id)).items
    definitions = {d.name: d for case in cases for d in case.definitions}
    edge = definitions["powers"]
    assert isinstance(edge.body, RelationshipDefinition)
    assert edge.body.source_concept_id == definitions["panel"].id
    assert edge.body.target_concept_id == definitions["motor"].id
    assert _QUALIFIER in edge.meaning
    (witness,) = edge.evidence
    excerpt = await project.get_evidence(evidence=witness)
    if expected is not None:
        assert witness.locator == expected
        assert isinstance(excerpt.part, ParsedTable)
        assert excerpt.part.rows == ((_ACTOR, "powers", _TARGET, _QUALIFIER, 7),)
    else:
        assert _ASSERTION in excerpt.excerpt
        assert isinstance(witness.locator, DocumentSpan)
        assert witness.locator.page == 2  # noqa: PLR2004 - The raster page is the second page.
