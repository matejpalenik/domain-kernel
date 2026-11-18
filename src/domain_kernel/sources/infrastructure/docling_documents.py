"""Optional Docling conversion of acquired PDF and Word inputs."""

from __future__ import annotations

from hashlib import file_digest
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, final, override, runtime_checkable

from domain_kernel.shared.errors import MissingCapabilityError, ResourceLimitError, SourceReadError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.validation import require_exact
from domain_kernel.sources.application.contracts import PDF, Word
from domain_kernel.sources.application.ports import FormatParser
from domain_kernel.sources.domain.parsed import DocumentSpan, ParsedTable, ParsedText

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from docling_core.transforms.chunker.base import BaseChunker

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


class _Document(Protocol):
    def iterate_items(self) -> Iterator[tuple[object, int]]: ...


class _FailureCategory(Protocol):
    @property
    def value(self) -> str: ...


class _Failure(Protocol):
    @property
    def category(self) -> _FailureCategory | None: ...


class _DocumentInput(Protocol):
    @property
    def page_count(self) -> int: ...


class _Result(Protocol):
    @property
    def status(self) -> _FailureCategory: ...
    @property
    def document(self) -> _Document: ...
    @property
    def errors(self) -> Sequence[_Failure]: ...
    @property
    def input(self) -> _DocumentInput: ...


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


class _Formats(Protocol):
    @property
    def PDF(self) -> str: ...  # noqa: N802 - Docling format enum member.
    @property
    def DOCX(self) -> str: ...  # noqa: N802 - Docling format enum member.


@runtime_checkable
class _Docling(Protocol):
    @property
    def InputFormat(self) -> _Formats: ...  # noqa: N802 - Docling type.
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


def _assets_digest(*, directory: Path, ocr: bool) -> str:
    configured = [
        directory / "docling-project--docling-layout-heron",
        directory / "docling-project--docling-models",
    ]
    if ocr:
        configured.append(directory / "RapidOcr")
    try:
        files: list[tuple[str, str]] = []
        for folder in configured:
            if not folder.is_dir() or folder.is_symlink():
                raise MissingCapabilityError(message=_MISSING_MODELS)
            found = False
            for path in sorted(folder.rglob("*")):
                relative = path.relative_to(directory)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                if path.is_symlink():
                    raise MissingCapabilityError(message=_MISSING_MODELS)
                if path.is_file():
                    found = True
                    with path.open("rb") as stream:
                        files.append(
                            (relative.as_posix(), file_digest(stream, "sha256").hexdigest())
                        )
            if not found:
                raise MissingCapabilityError(message=_MISSING_MODELS)
    except OSError:
        raise MissingCapabilityError(message=_MISSING_MODELS) from None
    return hash_json(value=tuple(files)).value


def _page_ranges(
    *, descriptor: FileDescriptor, limits: ProcessingLimits
) -> tuple[tuple[int, int], ...]:
    if not isinstance(descriptor, PDF) or descriptor.pages is None:
        return ((1, limits.max_pages),)
    ranges: list[tuple[int, int]] = []
    for page in sorted(descriptor.pages):
        if page > limits.max_pages:
            raise ResourceLimitError(message="Select PDF pages within the configured limit.")
        if ranges and page == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], page)
        else:
            ranges.append((page, page))
    return tuple(ranges)


def _convert(
    *,
    converter: _Converter,
    docling: _Docling,
    payload: bytes,
    descriptor: FileDescriptor,
    limits: ProcessingLimits,
) -> Iterator[_Document]:
    extension = "pdf" if isinstance(descriptor, PDF) else "docx"
    for page_range in _page_ranges(descriptor=descriptor, limits=limits):
        try:
            with BytesIO(payload) as stream:
                result = converter.convert(
                    source=docling.DocumentStream(name=f"source.{extension}", stream=stream),
                    max_file_size=limits.max_source_bytes,
                    max_num_pages=limits.max_pages,
                    page_range=page_range,
                    raises_on_error=False,
                )
        except (OSError, RuntimeError, ValueError):
            raise SourceReadError(
                message="Check the document format and the configured Docling models."
            ) from None
        if result.status.value != "success":
            categories = {
                error.category.value for error in result.errors if error.category is not None
            }
            if result.input.page_count > limits.max_pages or categories.intersection(
                {"timeout", "capacity"}
            ):
                raise ResourceLimitError(
                    message="Keep the document within the configured parser limits."
                )
            raise SourceReadError(
                message="Supply a complete document and select existing PDF pages."
            )
        yield result.document


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


def _parts(
    *,
    document: _Document,
    pdf: bool,
    limits: ProcessingLimits,
) -> Iterator[ParsedText | ParsedTable]:
    pages: dict[int, list[str]] = {}
    heading: str | None = None
    offset = table_number = 0
    for item, _ in document.iterate_items():
        if isinstance(item, _Text):
            text = item.text.strip()
            if not text:
                continue
            if pdf and item.prov:
                pages.setdefault(item.prov[0].page_no, []).append(text)
                continue
            if item.label in {"section_header", "title"}:
                heading = text[:512]
            yield ParsedText(
                text=text,
                locator=DocumentSpan(section=heading, start=offset, end=offset + len(text)),
            )
            offset += len(text) + 1
        elif isinstance(item, _Table):
            table_number += 1
            if table_number > limits.max_tables:
                raise ResourceLimitError(
                    message="Keep document tables within the configured limit."
                )
            yield _document_table(table=item, number=table_number, limits=limits)
    for page, lines in sorted(pages.items()):
        text = "\n".join(lines)
        if any(character.isalnum() for character in text):
            yield ParsedText(text=text, locator=DocumentSpan(page=page, start=0, end=len(text)))


def _validate_custom_chunker(*, chunker: object, fingerprint: str | None) -> None:
    from docling_core.transforms.chunker.base import BaseChunker  # noqa: PLC0415 -- optional integration

    if not isinstance(chunker, BaseChunker) or not fingerprint or not fingerprint.strip():
        raise ValueError("Supply a Docling chunker and its versioned configuration fingerprint.")


@final
class DoclingParser(FormatParser):
    """Convert explicitly supplied documents with a configured Docling pipeline."""

    def __init__(self, *, artifacts_path: Path | None = None, ocr: bool = False) -> None:
        """Select the native pipeline or local layout, table, and optional English OCR models."""
        require_exact(value=ocr, expected=bool, field="Enable document OCR")
        if ocr and artifacts_path is None:
            raise MissingCapabilityError(message=_MISSING_MODELS)
        self._artifacts_path = None if artifacts_path is None else Path(artifacts_path)
        self._ocr = ocr
        self._chunking: Literal["hybrid", "hierarchical"] | BaseChunker | None = None
        self._chunker_fingerprint: str | None = None
        self._chunk_tokens = 2048

    @classmethod
    def for_discovery(
        cls,
        *,
        chunking: Literal["hybrid", "hierarchical"] | BaseChunker = "hybrid",
        chunker_fingerprint: str | None = None,
        chunk_tokens: int = 2048,
        artifacts_path: Path | None = None,
        ocr: bool = False,
    ) -> DoclingParser:
        """Capture native document chunks alongside the original evidence."""
        if type(chunk_tokens) is not int or chunk_tokens < 1:
            raise ValueError("Supply a positive chunk token limit.")
        if isinstance(chunking, str):
            if chunking not in ("hybrid", "hierarchical") or chunker_fingerprint is not None:
                raise ValueError("Choose hybrid or hierarchical for a built-in chunker.")
        else:
            _validate_custom_chunker(chunker=chunking, fingerprint=chunker_fingerprint)
        parser = cls(artifacts_path=artifacts_path, ocr=ocr)
        parser._chunking = chunking
        parser._chunker_fingerprint = chunker_fingerprint
        parser._chunk_tokens = chunk_tokens
        return parser

    @property
    @override
    def parser_id(self) -> str:
        """Identify the configured document conversion semantics."""
        if self._artifacts_path is None:
            return "domain-kernel/docling-native-v1"
        return (
            "domain-kernel/docling-layout-ocr-v1"
            if self._ocr
            else "domain-kernel/docling-layout-v1"
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
        if self._artifacts_path is None:
            return versions + self._chunk_version
        assets = _assets_digest(directory=self._artifacts_path, ocr=self._ocr)
        return f"{versions}/{assets}{self._chunk_version}"

    @property
    def _chunk_version(self) -> str:
        if self._chunking is None:
            return ""
        if self._chunker_fingerprint is not None:
            return f"/custom/{self._chunker_fingerprint}"
        if self._chunking == "hierarchical":
            return "/hierarchical-v1"
        return f"/hybrid-v1/o200k_base/{self._chunk_tokens}/{version('tiktoken')}"

    def _chunks(self, *, document: object) -> Iterator[ParsedText]:
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
        for index, chunk in enumerate(chunker.chunk(dl_doc=document)):
            if not isinstance(chunk, DocChunk):
                raise SourceReadError(message="Docling chunk is missing native source references.")
            if not chunk.text.strip():
                continue
            items = chunk.meta.doc_items
            if not items:
                raise SourceReadError(message="Docling chunk is missing its source document items.")
            pages = sorted({p.page_no for item in items for p in item.prov})
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
        accelerator = _load(module="docling.datamodel.accelerator_options")
        if not isinstance(accelerator, _Accelerator):
            raise MissingCapabilityError(message=_MISSING_EXTRA)
        return docling.PdfFormatOption(
            pipeline_options=options.PdfPipelineOptions(
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
            ),
        )

    @override
    def parse(
        self, *, content: AcquiredSource, descriptor: FileDescriptor, limits: ProcessingLimits
    ) -> Iterator[ParsedText | ParsedTable]:
        """Convert bytes through the selected local Docling PDF or Word pipeline."""
        if not isinstance(descriptor, (PDF, Word)):
            raise TypeError("Select a PDF or Word source for the Docling parser.")
        payload = content.stream.read(size=limits.max_source_bytes + 1)
        if len(payload) > limits.max_source_bytes:
            raise ResourceLimitError
        docling = _load(module="docling.document_converter")
        if not isinstance(docling, _Docling):
            raise MissingCapabilityError(message=_MISSING_EXTRA)
        pdf = isinstance(descriptor, PDF)
        selected = docling.InputFormat.PDF if pdf else docling.InputFormat.DOCX
        converter = docling.DocumentConverter(
            allowed_formats=[selected],
            format_options={selected: self._pdf_options(docling=docling)} if pdf else {},
        )
        emitted = False
        for document in _convert(
            converter=converter,
            docling=docling,
            payload=payload,
            descriptor=descriptor,
            limits=limits,
        ):
            for part in _parts(document=document, pdf=pdf, limits=limits):
                emitted = True
                yield part
            if self._chunking is not None:
                yield from self._chunks(document=document)
        if not emitted:
            message = (
                "Configure local Docling OCR assets for scanned PDF pages."
                if pdf and not self._ocr
                else "Supply a document with readable text or tables."
            )
            raise SourceReadError(message=message)
