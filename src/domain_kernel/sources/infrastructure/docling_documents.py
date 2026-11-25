"""Optional local Docling conversion of verified document inputs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import file_digest
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path, PurePosixPath
from shutil import which
from subprocess import CalledProcessError, TimeoutExpired
from typing import TYPE_CHECKING, Literal, Protocol, final, override, runtime_checkable
from zipfile import BadZipFile

from domain_kernel.shared.errors import MissingCapabilityError, ResourceLimitError, SourceReadError
from domain_kernel.shared.hashing import canonical_json_bytes, hash_json
from domain_kernel.shared.validation import require_exact
from domain_kernel.sources.application.contracts import CSV, PDF, Document, Excel, document_kind
from domain_kernel.sources.application.ports import FormatParser
from domain_kernel.sources.domain.coverage import CoverageStatus, CoverageUnit
from domain_kernel.sources.domain.document_formats import (
    DOCUMENT_EXTENSIONS,
    DocumentFormat,
    document_extension,
)
from domain_kernel.sources.domain.parsed import DocumentSpan, ParsedTable, ParsedText
from domain_kernel.sources.infrastructure.docling_tables import (
    check_workbook,
    csv_options,
    csv_payload,
    empty_table_unit,
    excel_options,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from docling.datamodel.base_models import Page
    from docling_core.transforms.chunker.base import BaseChunker
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.types.doc.items.key_value import KeyValueItem

    from domain_kernel.sources.application.contracts import FileDescriptor
    from domain_kernel.sources.application.ports import AcquiredSource
    from domain_kernel.sources.domain.models import ProcessingLimits


_MISSING_EXTRA = "Install the Domain Kernel documents extra."
_MISSING_MODELS = (
    "Provision the selected Docling models in the configured local artifacts directory."
)
_CONVERSION_TIMEOUT = 60


class _Provenance(Protocol):
    @property
    def page_no(self) -> int: ...


@runtime_checkable
class _Text(Protocol):
    @property
    def text(self) -> str: ...
    @property
    def label(self) -> str: ...
    @property
    def prov(self) -> Sequence[_Provenance]: ...


@runtime_checkable
class _TrackSource(Protocol):
    @property
    def start_time(self) -> float: ...
    @property
    def end_time(self) -> float: ...


@runtime_checkable
class _MediaItem(Protocol):
    @property
    def source(self) -> Sequence[object]: ...


@runtime_checkable
class _Region(Protocol):
    @property
    def label(self) -> str: ...
    @property
    def self_ref(self) -> str: ...
    @property
    def prov(self) -> Sequence[_Provenance]: ...


class _Cell(Protocol):
    @property
    def text(self) -> str: ...
    @property
    def column_header(self) -> bool: ...


class _Data(Protocol):
    @property
    def num_rows(self) -> int: ...
    @property
    def num_cols(self) -> int: ...
    @property
    def grid(self) -> Sequence[Sequence[_Cell]]: ...


@runtime_checkable
class _Table(Protocol):
    @property
    def data(self) -> _Data: ...
    @property
    def prov(self) -> Sequence[_Provenance]: ...


class _FailureCategory(Protocol):
    @property
    def value(self) -> str: ...


class _Failure(Protocol):
    @property
    def category(self) -> _FailureCategory | None: ...
    @property
    def page_no(self) -> int | None: ...


class _DocumentInput(Protocol):
    @property
    def page_count(self) -> int: ...


class _Result(Protocol):
    @property
    def status(self) -> _FailureCategory: ...
    @property
    def document(self) -> DoclingDocument: ...
    @property
    def errors(self) -> Sequence[_Failure]: ...
    @property
    def input(self) -> _DocumentInput: ...
    @property
    def pages(self) -> Sequence[Page]: ...


class _Converter(Protocol):
    def convert(
        self,
        *,
        source: object,
        max_file_size: int,
        max_num_pages: int,
        page_range: tuple[int, int],
        raises_on_error: bool,
    ) -> _Result: ...


@runtime_checkable
class _Docling(Protocol):
    def InputFormat(self, value: str, /) -> str: ...  # noqa: N802 - Docling type.
    def DocumentStream(self, *, name: str, stream: BytesIO) -> object: ...  # noqa: N802
    def DocumentConverter(  # noqa: N802 - Docling constructor.
        self,
        *,
        allowed_formats: list[str],
        format_options: dict[str, object],
    ) -> _Converter: ...
    def NativePdfFormatOption(self, *, pipeline_options: object) -> object: ...  # noqa: N802
    def PdfFormatOption(self, *, pipeline_options: object) -> object: ...  # noqa: N802


@runtime_checkable
class _PipelineOptions(Protocol):
    def NativePdfPipelineOptions(  # noqa: N802 - Docling constructor.
        self,
        *,
        parser_threads: int,
        document_timeout: int,
    ) -> object: ...
    def PdfPipelineOptions(  # noqa: N802, PLR0913 - Exact upstream constructor.
        self,
        *,
        artifacts_path: Path,
        accelerator_options: object,
        document_timeout: int,
        enable_remote_services: bool,
        do_ocr: bool,
        do_table_structure: bool,
        ocr_options: object,
    ) -> object: ...
    def RapidOcrOptions(  # noqa: N802 - Docling constructor.
        self,
        *,
        lang: list[str],
        backend: str,
        force_full_page_ocr: bool,
    ) -> object: ...


@runtime_checkable
class _Accelerator(Protocol):
    def AcceleratorOptions(self, *, num_threads: int, device: str) -> object: ...  # noqa: N802


def _load(*, module: str) -> object:
    try:
        return import_module(name=module)
    except ImportError:
        raise MissingCapabilityError(message=_MISSING_EXTRA) from None


def _directory_digest(*, directory: Path, folders: Sequence[Path], missing: str) -> str:
    try:
        files: list[tuple[str, str]] = []
        for folder in folders:
            if not folder.is_dir() or folder.is_symlink():
                raise MissingCapabilityError(message=missing)
            found = False
            for path in sorted(folder.rglob("*")):
                relative = path.relative_to(directory)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                if path.is_symlink():
                    raise MissingCapabilityError(message=missing)
                if path.is_file():
                    found = True
                    with path.open("rb") as stream:
                        files.append(
                            (relative.as_posix(), file_digest(stream, "sha256").hexdigest())
                        )
            if not found:
                raise MissingCapabilityError(message=missing)
    except OSError:
        raise MissingCapabilityError(message=missing) from None
    return hash_json(value=tuple(files)).value


def _assets_digest(*, directory: Path, ocr: bool) -> str:
    folders = [
        directory / "docling-project--docling-layout-heron",
        directory / "docling-project--docling-models",
    ]
    if ocr:
        folders.append(directory / "RapidOcr")
    return _directory_digest(directory=directory, folders=folders, missing=_MISSING_MODELS)


def _page_range(*, descriptor: FileDescriptor, limits: ProcessingLimits) -> tuple[int, int]:
    if not isinstance(descriptor, PDF) or descriptor.pages is None:
        return (1, limits.max_pages)
    end = max(descriptor.pages)
    if end > limits.max_pages:
        raise ResourceLimitError(message="Select PDF pages within the configured limit.")
    return min(descriptor.pages), end


@dataclass(frozen=True, kw_only=True)
class _Conversion:
    document: DoclingDocument
    selected_pages: tuple[int, ...]
    page_status: Mapping[int, CoverageStatus]
    deferred_media: bool


def _pdf_page_status(*, result: _Result, selected: Sequence[int]) -> dict[int, CoverageStatus]:
    status: dict[int, CoverageStatus] = {}
    for page in result.pages:
        parsed = page.parsed_page
        if (
            parsed is not None
            and parsed.has_lines
            and not (parsed.textline_cells or parsed.bitmap_resources)
        ):
            status[page.page_no] = CoverageStatus.EMPTY
    for error in result.errors:
        deferred = error.category is not None and error.category.value in {"timeout", "capacity"}
        outcome = CoverageStatus.DEFERRED if deferred else CoverageStatus.UNREADABLE
        if error.page_no is not None:
            status[error.page_no] = outcome
        elif deferred:
            for number in selected:
                _ = status.setdefault(number, outcome)
    return status


def _convert(  # noqa: PLR0913 - One bounded conversion request.
    *,
    converter: _Converter,
    docling: _Docling,
    payload: bytes,
    name: str,
    descriptor: FileDescriptor,
    limits: ProcessingLimits,
    kind: DocumentFormat,
) -> _Conversion:
    page_range = _page_range(descriptor=descriptor, limits=limits)
    try:
        with BytesIO(payload) as stream:
            result = converter.convert(
                source=docling.DocumentStream(name=name, stream=stream),
                max_file_size=max(limits.max_source_bytes, len(payload)),
                max_num_pages=limits.max_pages,
                page_range=page_range,
                raises_on_error=False,
            )
    except ImportError:
        raise MissingCapabilityError(
            message=f"Install the Docling backend for {kind.value}."
        ) from None
    except TimeoutExpired:
        raise ResourceLimitError(
            message=f"Docling conversion timed out for {kind.value}."
        ) from None
    except CalledProcessError:
        raise SourceReadError(
            message=f"The local converter could not open the {kind.value} source."
        ) from None
    except (OSError, RuntimeError, ValueError):
        raise SourceReadError(
            message="Check the document format and the configured Docling models."
        ) from None
    return _conversion(
        result=result, kind=kind, descriptor=descriptor, limits=limits, page_range=page_range
    )


def _conversion(
    *,
    result: _Result,
    kind: DocumentFormat,
    descriptor: FileDescriptor,
    limits: ProcessingLimits,
    page_range: tuple[int, int],
) -> _Conversion:
    paginated = kind in (DocumentFormat.PDF, DocumentFormat.IMAGE, DocumentFormat.METS_GBS)
    partial = result.status.value == "partial_success" and (
        paginated or kind in (DocumentFormat.AUDIO, DocumentFormat.VIDEO)
    )
    if result.status.value != "success" and not partial:
        categories = {error.category.value for error in result.errors if error.category is not None}
        if result.input.page_count > limits.max_pages or categories.intersection(
            {"timeout", "capacity"}
        ):
            raise ResourceLimitError(
                message="Keep the document within the configured parser limits."
            )
        raise SourceReadError(
            message=f"Supply a readable {kind.value} source and valid selections."
        )
    start, end = page_range
    last = min(end, result.input.page_count) if paginated else 0
    if isinstance(descriptor, PDF) and descriptor.pages is not None and last < end:
        raise SourceReadError(message="Select existing PDF pages.")
    if isinstance(descriptor, PDF) and descriptor.pages is not None:
        selected = tuple(sorted(descriptor.pages))
    elif paginated:
        selected = tuple(range(start, last + 1))
    else:
        selected = tuple(sorted(result.document.pages))
    if selected and (len(selected) > limits.max_pages or selected[-1] > limits.max_pages):
        raise ResourceLimitError(message="Keep the document within the configured page limit.")
    return _Conversion(
        document=result.document,
        selected_pages=selected,
        page_status=(
            _pdf_page_status(result=result, selected=selected)
            if paginated
            else dict.fromkeys(selected, CoverageStatus.EMPTY)
        ),
        deferred_media=partial and kind in (DocumentFormat.AUDIO, DocumentFormat.VIDEO),
    )


def _document_table(*, table: _Table, number: int, limits: ProcessingLimits) -> ParsedTable:
    data = table.data
    if data.num_rows * data.num_cols > limits.max_table_cells:
        raise ResourceLimitError(message="Keep document table cells within the configured limit.")
    grid = data.grid
    width = data.num_cols
    header = grid[0] if grid and all(cell.column_header for cell in grid[0]) else ()
    fields = tuple(
        f"{index + 1}: {header[index].text}" if header else f"Column {index + 1}"
        for index in range(width)
    )
    rows = tuple(tuple(cell.text or None for cell in row) for row in grid[bool(header) :])
    page = table.prov[0].page_no if table.prov else None
    name = f"Page {page} table {number}" if page is not None else f"Table {number}"
    return ParsedTable(
        name=name,
        columns=fields,
        rows=rows,
        locator=DocumentSpan(page=page, section=name, start=0, end=max(1, len(rows))),
    )


def _section(*, item: _Text, heading: str | None) -> str | None:
    if isinstance(item, _MediaItem):
        for track in item.source:
            if isinstance(track, _TrackSource):
                return f"media/{track.start_time:.6f}/{track.end_time:.6f}"
    return heading


def _page(*, document_item: _Text | _Table | _Region) -> int | None:
    return document_item.prov[0].page_no if document_item.prov else None


def _page_parts(
    *,
    selected: Sequence[int],
    lines: Mapping[int, list[str]],
    table_pages: set[int],
    picture_pages: set[int],
    page_status: Mapping[int, CoverageStatus],
) -> Iterator[ParsedText | CoverageUnit]:
    for page in selected:
        text = "\n".join(lines.get(page, ()))
        status = page_status.get(page)
        if text:
            yield ParsedText(text=text, locator=DocumentSpan(page=page, start=0, end=len(text)))
        elif page not in table_pages:
            yield CoverageUnit(
                locator=DocumentSpan(page=page, start=0, end=1),
                status=(
                    CoverageStatus.UNSUPPORTED
                    if status is CoverageStatus.EMPTY and page in picture_pages
                    else status or CoverageStatus.UNREADABLE
                ),
            )
            continue
        if status is CoverageStatus.DEFERRED or status is CoverageStatus.UNREADABLE:
            yield CoverageUnit(
                locator=DocumentSpan(page=page, section="incomplete", start=0, end=1),
                status=status,
            )


def _key_value_parts(*, item: KeyValueItem) -> Iterator[ParsedText]:
    links: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for link in item.graph.links:
        links[link.source_cell_id].append((link.label.value, link.target_cell_id))
    for index, cell in enumerate(item.graph.cells):
        text = canonical_json_bytes(
            value={
                "cell": cell.cell_id,
                "role": cell.label.value,
                "text": cell.text,
                "outgoing_links": tuple(links.get(cell.cell_id, ())),
            }
        ).decode()
        yield ParsedText(
            text=text,
            locator=DocumentSpan(
                page=cell.prov.page_no if cell.prov is not None else None,
                section=f"item/{item.self_ref}/cells",
                start=index,
                end=index + 1,
            ),
        )


def _parts(  # noqa: C901, PLR0912 - One ordered traversal preserves headings and page attribution.
    *,
    converted: _Conversion,
    limits: ProcessingLimits,
) -> Iterator[ParsedText | ParsedTable | CoverageUnit]:
    from docling_core.types.doc.common.content_layer import ContentLayer  # noqa: PLC0415
    from docling_core.types.doc.items.key_value import KeyValueItem  # noqa: PLC0415

    pages: dict[int, list[str]] = {}
    table_pages: set[int] = set()
    picture_pages: set[int] = set()
    selected = set(converted.selected_pages)
    heading: str | None = None
    offset = table_number = 0
    for item, _ in converted.document.iterate_items(included_content_layers=set(ContentLayer)):
        if isinstance(item, _Text):
            text = item.text.strip()
            if not text:
                continue
            page = _page(document_item=item)
            if selected and page is not None:
                if page in selected:
                    pages.setdefault(page, []).append(text)
                continue
            if item.label in {"section_header", "title"}:
                heading = text[:512]
            yield ParsedText(
                text=text,
                locator=DocumentSpan(
                    page=page,
                    section=_section(item=item, heading=heading),
                    start=offset,
                    end=offset + len(text),
                ),
            )
            offset += len(text) + 1
        elif isinstance(item, _Table):
            page = _page(document_item=item)
            if selected and page not in selected:
                continue
            table_number += 1
            if table_number > limits.max_tables:
                raise ResourceLimitError(
                    message="Keep document tables within the configured limit."
                )
            if page is not None:
                table_pages.add(page)
            yield _document_table(table=item, number=table_number, limits=limits)
        elif isinstance(item, KeyValueItem):
            yield from _key_value_parts(item=item)
        elif isinstance(item, _Region) and item.label in {"picture", "formula"}:
            page = _page(document_item=item)
            if not selected or page in selected:
                if page is not None:
                    picture_pages.add(page)
                yield CoverageUnit(
                    locator=DocumentSpan(
                        page=page, section=f"item/{item.self_ref}", start=0, end=1
                    ),
                    status=CoverageStatus.UNSUPPORTED,
                )
    yield from _page_parts(
        selected=converted.selected_pages,
        lines=pages,
        table_pages=table_pages,
        picture_pages=picture_pages,
        page_status=converted.page_status,
    )


def _validate_custom_chunker(*, chunker: object, fingerprint: str | None) -> None:
    from docling_core.transforms.chunker.base import BaseChunker  # noqa: PLC0415 -- optional integration

    if not isinstance(chunker, BaseChunker) or not fingerprint or not fingerprint.strip():
        raise ValueError("Supply a Docling chunker and its versioned configuration fingerprint.")


def _covered_parts(
    *, converted: _Conversion, limits: ProcessingLimits
) -> Iterator[ParsedText | ParsedTable | CoverageUnit]:
    parts = _parts(converted=converted, limits=limits)
    first = next(parts, None)
    if first is not None:
        yield first
        yield from parts
    if converted.deferred_media:
        yield CoverageUnit(
            locator=DocumentSpan(section="media/untranscribed", start=0, end=1),
            status=CoverageStatus.DEFERRED,
        )
    elif first is None:
        yield CoverageUnit(locator=DocumentSpan(start=0, end=1), status=CoverageStatus.EMPTY)


_LEGACY_OFFICE = {DocumentFormat.DOC, DocumentFormat.XLS, DocumentFormat.PPT, DocumentFormat.RTF}
_TRANSCRIPTS = {DocumentFormat.AUDIO, DocumentFormat.VIDEO, DocumentFormat.VTT}
_OPTIONAL_BACKENDS = {
    DocumentFormat.ODT: "odfdo",
    DocumentFormat.ODS: "odfdo",
    DocumentFormat.ODP: "odfdo",
    DocumentFormat.XML_XBRL: "arelle",
}
_MISSING_TAXONOMY = "Configure a local XBRL taxonomy directory for Docling."


def _prerequisites(*, kind: DocumentFormat) -> None:
    if kind in _LEGACY_OFFICE and which("soffice") is None and which("libreoffice") is None:
        raise MissingCapabilityError(message=f"Install LibreOffice for {kind.value} files.")
    if kind in _OPTIONAL_BACKENDS and find_spec(_OPTIONAL_BACKENDS[kind]) is None:
        raise MissingCapabilityError(
            message=f"Install the documents-specialty extra for {kind.value} files."
        )


def _ebcdic_options(*, descriptor: Document) -> object:
    from docling.datamodel.backend_options import EbcdicBackendOptions  # noqa: PLC0415
    from docling.document_converter import EbcdicFormatOption  # noqa: PLC0415

    return EbcdicFormatOption(
        backend_options=EbcdicBackendOptions.model_validate({"layout": descriptor.record_layout})
    )


def _xbrl_options(*, taxonomy: Path | None) -> object:
    if taxonomy is None or not taxonomy.is_dir():
        raise MissingCapabilityError(message=_MISSING_TAXONOMY)
    from docling.datamodel.backend_options import XBRLBackendOptions  # noqa: PLC0415
    from docling.document_converter import XBRLFormatOption  # noqa: PLC0415

    return XBRLFormatOption(
        backend_options=XBRLBackendOptions.model_validate(
            {
                "taxonomy": taxonomy,
                "enable_local_fetch": True,
                "enable_remote_fetch": False,
            }
        )
    )


def _media_options(*, checkpoint: Path | None) -> object:
    if checkpoint is None or not checkpoint.is_file():
        raise MissingCapabilityError(
            message="Configure a local Whisper checkpoint for audio or video."
        )
    if which("ffmpeg") is None or find_spec("whisper") is None:
        raise MissingCapabilityError(
            message="Install ffmpeg and the documents-media extra for audio or video."
        )
    from docling.datamodel.asr_model_specs import WHISPER_TINY_NATIVE  # noqa: PLC0415
    from docling.datamodel.pipeline_options import AsrPipelineOptions  # noqa: PLC0415
    from docling.document_converter import AudioFormatOption  # noqa: PLC0415

    return AudioFormatOption(
        pipeline_options=AsrPipelineOptions(
            asr_options=WHISPER_TINY_NATIVE.model_copy(update={"repo_id": str(checkpoint)}),
            enable_remote_services=False,
            document_timeout=_CONVERSION_TIMEOUT,
        )
    )


@final
class DoclingParser(FormatParser):
    """Convert explicitly supplied documents with a configured Docling pipeline."""

    def __init__(
        self,
        *,
        artifacts_path: Path | None = None,
        ocr: bool = False,
        asr_model_path: Path | None = None,
        xbrl_taxonomy_path: Path | None = None,
    ) -> None:
        """Select the native pipeline or local layout, table, and optional English OCR models."""
        require_exact(value=ocr, expected=bool, field="Enable document OCR")
        if ocr and artifacts_path is None:
            raise MissingCapabilityError(message=_MISSING_MODELS)
        self._artifacts_path = None if artifacts_path is None else Path(artifacts_path)
        self._ocr = ocr
        self._asr_model_path = asr_model_path
        self._xbrl_taxonomy_path = xbrl_taxonomy_path
        self._chunking: Literal["hybrid", "hierarchical"] | BaseChunker | None = None
        self._chunker_fingerprint: str | None = None
        self._chunk_tokens = 2048

    @classmethod
    def for_discovery(  # noqa: PLR0913 - Exposes the explicit chunker and local model settings.
        cls,
        *,
        chunking: Literal["hybrid", "hierarchical"] | BaseChunker = "hybrid",
        chunker_fingerprint: str | None = None,
        chunk_tokens: int = 2048,
        artifacts_path: Path | None = None,
        ocr: bool = False,
        asr_model_path: Path | None = None,
        xbrl_taxonomy_path: Path | None = None,
    ) -> DoclingParser:
        """Capture native document chunks alongside the original evidence."""
        if type(chunk_tokens) is not int or chunk_tokens < 1:
            raise ValueError("Supply a positive chunk token limit.")
        if isinstance(chunking, str):
            if chunking not in ("hybrid", "hierarchical") or chunker_fingerprint is not None:
                raise ValueError("Choose hybrid or hierarchical for a built-in chunker.")
        else:
            _validate_custom_chunker(chunker=chunking, fingerprint=chunker_fingerprint)
        parser = cls(
            artifacts_path=artifacts_path,
            ocr=ocr,
            asr_model_path=asr_model_path,
            xbrl_taxonomy_path=xbrl_taxonomy_path,
        )
        parser._chunking = chunking
        parser._chunker_fingerprint = chunker_fingerprint
        parser._chunk_tokens = chunk_tokens
        return parser

    @property
    @override
    def parser_id(self) -> str:
        """Identify the configured document conversion semantics."""
        if self._artifacts_path is None:
            return "domain-kernel/docling-native-v2"
        return (
            "domain-kernel/docling-layout-ocr-v2"
            if self._ocr
            else "domain-kernel/docling-layout-v2"
        )

    @property
    @override
    def parser_version(self) -> str:
        """Identify the installed parser implementations and explicitly supplied model assets."""
        try:
            versions = "/".join(
                version(distribution_name=name)
                for name in ("docling", "docling-core", "docling-parse")
            )
        except PackageNotFoundError:
            raise MissingCapabilityError(message=_MISSING_EXTRA) from None
        if self._artifacts_path is not None:
            versions += f"/{_assets_digest(directory=self._artifacts_path, ocr=self._ocr)}"
        if self._asr_model_path is not None:
            try:
                with self._asr_model_path.open("rb") as checkpoint:
                    versions += f"/asr/{file_digest(checkpoint, 'sha256').hexdigest()}"
            except OSError:
                raise MissingCapabilityError(
                    message="Configure a readable local Whisper checkpoint."
                ) from None
        if (taxonomy := self._xbrl_taxonomy_path) is not None:
            fingerprint = _directory_digest(
                directory=taxonomy, folders=(taxonomy,), missing=_MISSING_TAXONOMY
            )
            versions += f"/xbrl/{fingerprint}"
        return versions + self._chunk_version

    @property
    def _chunk_version(self) -> str:
        if self._chunking is None:
            return ""
        if self._chunker_fingerprint is not None:
            return f"/custom/{self._chunker_fingerprint}"
        if self._chunking == "hierarchical":
            return "/hierarchical-v1"
        return f"/hybrid-v1/o200k_base/{self._chunk_tokens}/{version('tiktoken')}"

    def _chunks(  # noqa: C901 - Construct and validate native chunk provenance in one pass.
        self,
        *,
        document: object,
        selected_pages: Sequence[int],
    ) -> Iterator[ParsedText]:
        from docling_core.transforms.chunker.doc_chunk import DocChunk  # noqa: PLC0415 -- lazy optional chunking adapter
        from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker  # noqa: PLC0415 -- lazy optional chunking adapter
        from docling_core.types.doc.document import DoclingDocument  # noqa: PLC0415 -- lazy optional chunking adapter

        if not isinstance(document, DoclingDocument):
            raise SourceReadError(message="Expected a native Docling document for chunking.")
        if self._chunking == "hybrid":
            from docling_core.transforms.chunker.hybrid_chunker import HybridChunker  # noqa: PLC0415 -- lazy optional chunking adapter
            from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer  # noqa: PLC0415 -- lazy optional chunking adapter
            from tiktoken import get_encoding  # noqa: PLC0415 -- lazy optional chunking adapter

            chunker = HybridChunker(
                tokenizer=OpenAITokenizer(
                    tokenizer=get_encoding("o200k_base"),
                    max_tokens=self._chunk_tokens,
                )
            )
        elif self._chunking == "hierarchical":
            chunker = HierarchicalChunker()
        elif self._chunking is not None:
            chunker = self._chunking
        else:
            return
        selected = set(selected_pages)
        for index, chunk in enumerate(chunker.chunk(dl_doc=document)):
            if not isinstance(chunk, DocChunk):
                raise SourceReadError(message="Docling chunk is missing native source references.")
            if not chunk.text.strip():
                continue
            items = chunk.meta.doc_items
            if not items:
                raise SourceReadError(message="Docling chunk is missing its source document items.")
            pages = sorted({p.page_no for item in items for p in item.prov})
            if selected and (not pages or not selected.issuperset(pages)):
                continue
            digest = hash_json(value=tuple(item.self_ref for item in items))
            refs = f"{items[0].self_ref}..{items[-1].self_ref}/{digest.value}"
            section = f"docling-chunk/{index}/pages/{','.join(map(str, pages))}/items/{refs}"
            if chunk.meta.headings:
                section = (section + "/heading/" + " / ".join(chunk.meta.headings))[:512]
            yield ParsedText(
                text=chunk.text,
                locator=DocumentSpan(
                    page=pages[0] if len(pages) == 1 else None,
                    section=section,
                    start=0,
                    end=len(chunk.text),
                ),
            )

    def _pdf_options(self, *, docling: _Docling) -> object:
        options = _load(module="docling.datamodel.pipeline_options")
        if not isinstance(options, _PipelineOptions):
            raise MissingCapabilityError(message=_MISSING_EXTRA)
        if self._artifacts_path is None:
            return docling.NativePdfFormatOption(
                pipeline_options=options.NativePdfPipelineOptions(
                    parser_threads=1,
                    document_timeout=_CONVERSION_TIMEOUT,
                ),
            )
        return docling.PdfFormatOption(pipeline_options=self._layout_options())

    def _layout_options(self) -> object:
        if self._artifacts_path is None:
            raise MissingCapabilityError(message=_MISSING_MODELS)
        options = _load(module="docling.datamodel.pipeline_options")
        if not isinstance(options, _PipelineOptions):
            raise MissingCapabilityError(message=_MISSING_EXTRA)
        accelerator = _load(module="docling.datamodel.accelerator_options")
        if not isinstance(accelerator, _Accelerator):
            raise MissingCapabilityError(message=_MISSING_EXTRA)
        return options.PdfPipelineOptions(
            artifacts_path=self._artifacts_path,
            accelerator_options=accelerator.AcceleratorOptions(num_threads=1, device="cpu"),
            document_timeout=_CONVERSION_TIMEOUT,
            enable_remote_services=False,
            do_ocr=self._ocr,
            do_table_structure=True,
            ocr_options=options.RapidOcrOptions(
                lang=["en"],
                backend="torch",
                force_full_page_ocr=self._ocr,
            ),
        )

    @override
    def parse(
        self, *, content: AcquiredSource, descriptor: FileDescriptor, limits: ProcessingLimits
    ) -> Iterator[ParsedText | ParsedTable | CoverageUnit]:
        """Convert verified bytes using the corresponding local Docling backend."""
        kind = document_kind(descriptor=descriptor)
        if kind is None:
            raise TypeError("Select a Docling document descriptor.")
        _prerequisites(kind=kind)
        payload = content.stream.read(size=limits.max_source_bytes + 1)
        if len(payload) > limits.max_source_bytes:
            raise ResourceLimitError
        docling = _load(module="docling.document_converter")
        if not isinstance(docling, _Docling):
            raise MissingCapabilityError(message=_MISSING_EXTRA)
        selected = docling.InputFormat(kind.value)
        tables: list[ParsedTable] = []
        if kind is DocumentFormat.CSV:
            csv = (
                descriptor
                if isinstance(descriptor, CSV)
                else CSV(location=descriptor.resolved_location())
            )
            payload = csv_payload(raw=payload, descriptor=csv, limits=limits)
            option = csv_options(descriptor=csv, limits=limits, tables=tables)
        else:
            option = self._format_options(
                kind=kind,
                descriptor=descriptor,
                docling=docling,
                limits=limits,
                payload=payload,
                tables=tables,
            )
        converter = docling.DocumentConverter(
            allowed_formats=[selected],
            format_options={selected: option} if option is not None else {},
        )
        original_name = PurePosixPath(content.origin.location).name
        extension = document_extension(name=original_name)
        aliases = DOCUMENT_EXTENSIONS[kind]
        name = f"source.{extension if extension in aliases else aliases[0]}"
        converted = _convert(
            converter=converter,
            docling=docling,
            payload=payload,
            name=name,
            descriptor=descriptor,
            limits=limits,
            kind=kind,
        )
        if kind in (DocumentFormat.CSV, DocumentFormat.XLSX, DocumentFormat.XLS):
            for table in tables:
                yield table
                yield from empty_table_unit(table=table)
            return
        yield from _covered_parts(converted=converted, limits=limits)
        if self._chunking is not None and kind not in _TRANSCRIPTS:
            yield from self._chunks(
                document=converted.document, selected_pages=converted.selected_pages
            )

    def _format_options(  # noqa: PLR0913 - Configuration for a selected conversion.
        self,
        *,
        kind: DocumentFormat,
        descriptor: FileDescriptor,
        docling: _Docling,
        limits: ProcessingLimits,
        payload: bytes,
        tables: list[ParsedTable],
    ) -> object | None:
        if kind is DocumentFormat.PDF:
            return self._pdf_options(docling=docling)
        if kind in (DocumentFormat.IMAGE, DocumentFormat.METS_GBS):
            return self._visual_options(kind=kind)
        if kind in (DocumentFormat.XLSX, DocumentFormat.XLS):
            if kind is DocumentFormat.XLSX:
                try:
                    check_workbook(raw=payload, limits=limits)
                except (BadZipFile, ValueError, SyntaxError):
                    raise SourceReadError(message="Supply a valid Excel workbook.") from None
            return excel_options(
                sheets=descriptor.sheets if isinstance(descriptor, Excel) else None,
                header_row=descriptor.header_row if isinstance(descriptor, Excel) else 1,
                limits=limits,
                tables=tables,
            )
        if kind in (DocumentFormat.AUDIO, DocumentFormat.VIDEO, DocumentFormat.XML_XBRL):
            return (
                _xbrl_options(taxonomy=self._xbrl_taxonomy_path)
                if kind is DocumentFormat.XML_XBRL
                else _media_options(checkpoint=self._asr_model_path)
            )
        if isinstance(descriptor, Document) and kind is DocumentFormat.EBCDIC:
            return _ebcdic_options(descriptor=descriptor)
        return None

    def _visual_options(self, *, kind: DocumentFormat) -> object:
        if kind is DocumentFormat.IMAGE and not self._ocr:
            raise MissingCapabilityError(
                message="Configure local Docling layout and OCR assets for images."
            )
        from docling.datamodel.pipeline_options import PdfPipelineOptions  # noqa: PLC0415
        from docling.document_converter import ImageFormatOption, MetsGbsFormatOption  # noqa: PLC0415

        options = self._layout_options()
        if not isinstance(options, PdfPipelineOptions):
            raise MissingCapabilityError(message=_MISSING_EXTRA)
        if kind is DocumentFormat.METS_GBS:
            return MetsGbsFormatOption(pipeline_options=options)
        return ImageFormatOption(pipeline_options=options)
