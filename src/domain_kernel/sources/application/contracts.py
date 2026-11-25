"""Host-facing source descriptors and detached batch outcomes."""

from __future__ import annotations

from collections.abc import Sequence  # noqa: TC003 - Pydantic resolves descriptor schemas.
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 - Pydantic resolves statement fields.
from enum import StrEnum, unique
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import Field, StrictBool, field_validator, model_validator

from domain_kernel.configuration import ConfigurationModel, NonEmpty, PositiveInt
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.policies.naming import require_lookup_name, resolve_names
from domain_kernel.shared.hashing import JsonValue  # noqa: TC001 - Pydantic resolves record layouts.
from domain_kernel.shared.identifiers.content_hash import ContentHash  # noqa: TC001 - Runtime validation.
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.document_formats import DocumentFormat
from domain_kernel.sources.domain.models import IngestedSource
from domain_kernel.sources.domain.parsed import ParsedPart, ParsedPayload, ParsedSourceOrigin
from domain_kernel.sources.domain.paths import relative_parts, require_glob
from domain_kernel.sources.domain.statements import (
    Person,
    StatementForm,
    StatementIntent,
    require_statement_time,
)

if TYPE_CHECKING:
    from domain_kernel.shared.enums.issue_severity import IssueSeverity
    from domain_kernel.sources.domain.models import SourceRevision


class ReaderLocation(ConfigurationModel):
    """A reader-relative selection under one configured root or prefix."""

    reader: NonEmpty
    path: NonEmpty

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        _ = relative_parts(path=value, allow_root=True)
        return PurePosixPath(value).as_posix()


class FileInput(ConfigurationModel):
    """An exact source file selection independent of format options."""

    path: str | Path | None = None
    location: ReaderLocation | None = None
    expected_hash: ContentHash | None = None

    @model_validator(mode="after")
    def require_one_location(self) -> Self:
        """Resolve one file location and require safe relative components."""
        if (self.path is None) == (self.location is None):
            raise ValueError("Supply exactly one file path or reader location")
        _ = relative_parts(path=self.resolved_location().path)
        return self

    def resolved_location(self) -> ReaderLocation:
        """Resolve shorthand against the configured default reader."""
        if self.location is not None:
            return self.location
        if self.path is None:
            raise ValueError("Supply a file path or reader location")
        return ReaderLocation(
            reader="inputs",
            path=self.path.as_posix() if isinstance(self.path, Path) else self.path,
        )


class PDF(FileInput):
    """Acquire a PDF, with optional one-based pages for an installed parser."""

    format: Literal["pdf"] = "pdf"
    pages: Sequence[PositiveInt] | None = None

    @field_validator("pages")
    @classmethod
    def _pages(cls, value: Sequence[int] | None) -> tuple[int, ...] | None:
        if value is None:
            return None
        pages = tuple(value)
        if not pages or len(set(pages)) != len(pages):
            raise ValueError("Select distinct positive page numbers")
        return pages


class CSV(FileInput):
    """Acquire a delimited text source with explicit parser options."""

    format: Literal["csv"] = "csv"
    delimiter: Annotated[str, Field(min_length=1, max_length=1)] = ","
    encoding: NonEmpty = "utf-8"
    header_row: PositiveInt = 1


class Excel(FileInput):
    """Acquire an Excel workbook with explicit sheet and header choices."""

    format: Literal["excel"] = "excel"
    sheets: Sequence[NonEmpty] | None = None
    header_row: PositiveInt = 1

    @field_validator("sheets")
    @classmethod
    def _sheets(cls, value: Sequence[str] | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        sheets = tuple(value)
        if not sheets or len(set(sheets)) != len(sheets):
            raise ValueError("Select distinct workbook sheets")
        return sheets


class Word(FileInput):
    """Acquire a Word document."""

    format: Literal["word"] = "word"


class Document(FileInput):
    """Acquire a document in an explicitly selected Docling format."""

    format: Literal["document"] = "document"
    kind: DocumentFormat
    record_layout: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def _layout(self) -> Self:
        if (self.kind is DocumentFormat.EBCDIC) != (self.record_layout is not None):
            raise ValueError("Supply a record layout for EBCDIC inputs only")
        return self


class Ontology(FileInput):
    """Acquire an explicitly selected ontology serialization."""

    format: Literal["turtle", "rdfxml", "jsonld", "ntriples", "trig", "nquads"] = "turtle"


type FileDescriptor = Annotated[
    PDF | CSV | Excel | Word | Document | Ontology, Field(discriminator="format")
]


def document_kind(*, descriptor: FileDescriptor) -> DocumentFormat | None:
    """Select the matching Docling family for a public descriptor."""
    if isinstance(descriptor, Document):
        return descriptor.kind
    return _DOCUMENT_KINDS.get(descriptor.format)


_DOCUMENT_KINDS = {
    "pdf": DocumentFormat.PDF,
    "word": DocumentFormat.DOCX,
    "excel": DocumentFormat.XLSX,
    "csv": DocumentFormat.CSV,
}


class Statement(ConfigurationModel):
    """An attributed statement with an independently resolved recorder."""

    format: Literal["statement"] = "statement"
    text: NonEmpty = Field(repr=False)
    speaker: Person
    recorded_by: NonEmpty | None = None
    stated_at: datetime | None = None
    context: NonEmpty
    form: StatementForm
    intent: StatementIntent

    @field_validator("stated_at")
    @classmethod
    def _check_time(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            require_statement_time(value=value)
        return value


class ParsedSource(ConfigurationModel):
    """Accept a caller-provided normalized capture through its configured host provider."""

    origin: ParsedSourceOrigin
    parts: Sequence[ParsedPart]
    format: Literal["normalized"] = "normalized"

    @model_validator(mode="after")
    def _payload(self) -> Self:
        object.__setattr__(self, "parts", self.capture().parts)
        return self

    def capture(self) -> ParsedPayload:
        """Return the exact typed payload without invoking another parser."""
        return ParsedPayload(origin=self.origin, parts=self.parts)


type SourceDescriptor = Annotated[
    PDF | CSV | Excel | Word | Document | Ontology | ParsedSource | Statement,
    Field(discriminator="format"),
]


class CopyTo(ConfigurationModel):
    """Explicit destination for an immutable original-file copy."""

    store: NonEmpty


class SourceInput(ConfigurationModel):
    """One independently committed item in a batch source selection."""

    source: SourceDescriptor
    display_name: str | None = None
    name: str | None = None
    retain_original: CopyTo | None = None
    idempotency_key: NonEmpty | None = None

    @model_validator(mode="after")
    def _names(self) -> Self:
        _ = resolve_names(name=self.name, display_name=self.display_name)
        return self


class SourceFolder(ConfigurationModel):
    """A bounded reader selection with case-sensitive include and exclude filters."""

    location: ReaderLocation
    recursive: StrictBool = False
    include: Sequence[NonEmpty] = ()
    exclude: Sequence[NonEmpty] = ()
    name_prefix: str | None = None
    retain_original: CopyTo | None = None
    idempotency_key: NonEmpty | None = None

    @field_validator("include", "exclude")
    @classmethod
    def _patterns(cls, value: Sequence[str]) -> tuple[str, ...]:
        for pattern in value:
            require_glob(pattern=pattern)
        return tuple(value)

    @field_validator("name_prefix")
    @classmethod
    def _prefix(cls, value: str | None) -> str | None:
        if value is not None:
            require_lookup_name(name=value)
        return value


@unique
class SourceEntryKind(StrEnum):
    """Reader-reported kind of an immediate child."""

    FILE = "file"
    FOLDER = "folder"
    LINK = "link"


@dataclass(frozen=True, kw_only=True)
class SourceEntry:
    """Exact resolved listing metadata, independent of content integrity."""

    location: ReaderLocation
    kind: SourceEntryKind
    provider_scope: str
    provider_item_id: str | None = None
    provider_version: str | None = None

    def __post_init__(self) -> None:
        """Check declared provider and entry selection values."""
        RuntimeTypeValidation.require_exact(
            value=self.location, expected=ReaderLocation, field="Reader location"
        )
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=SourceEntryKind, field="Entry kind"
        )
        TextValidation.require_text(value=self.provider_scope, field="Provider scope")
        for value in (self.provider_item_id, self.provider_version):
            if value is not None:
                TextValidation.require_text(value=value, field="Provider token")


@unique
class IngestionStage(StrEnum):
    """The operation that raised a per-selection finding."""

    LISTING = "listing"
    NAMING = "naming"
    INGESTION = "ingestion"


@dataclass(frozen=True, kw_only=True)
class IngestionSuccess:
    """One accepted input in selection order."""

    input: SourceInput
    ingested_source: IngestedSource

    def __post_init__(self) -> None:
        """Require a resolved input and its typed success."""
        RuntimeTypeValidation.require_exact(
            value=self.input, expected=SourceInput, field="Source input"
        )
        RuntimeTypeValidation.require_exact(
            value=self.ingested_source, expected=IngestedSource, field="Ingested source"
        )


@dataclass(frozen=True, kw_only=True)
class IngestionFailure:
    """One actionable diagnostic with its precise input and optional location."""

    input: SourceInput | SourceFolder
    stage: IngestionStage
    issue: Issue
    retryable: bool
    location: ReaderLocation | None = None

    def __post_init__(self) -> None:
        """Keep location and diagnostics as structured values."""
        if type(self.input) not in (SourceInput, SourceFolder):
            raise TypeError("Use an inspected file or folder input")
        RuntimeTypeValidation.require_exact(
            value=self.stage, expected=IngestionStage, field="Ingestion stage"
        )
        RuntimeTypeValidation.require_exact(
            value=self.issue, expected=Issue, field="Ingestion issue"
        )
        RuntimeTypeValidation.require_exact(value=self.retryable, expected=bool, field="Retryable")
        if self.location is not None:
            RuntimeTypeValidation.require_exact(
                value=self.location, expected=ReaderLocation, field="Location"
            )

    @property
    def message(self) -> str:
        """Return the same sanitized issue message."""
        return self.issue.message

    @property
    def code(self) -> str:
        """Return the issue's stable code."""
        return self.issue.code

    @property
    def severity(self) -> IssueSeverity:
        """Return the exact issue severity."""
        return self.issue.severity


@dataclass(frozen=True, kw_only=True)
class BatchIngestionResult:
    """Detached outcomes ordered by input and reader-relative path."""

    items: Sequence[IngestionSuccess | IngestionFailure]

    def __post_init__(self) -> None:
        """Snapshot a sequence of exact item outcomes."""
        if not SequenceValidation.is_non_string_sequence(value=self.items):
            raise TypeError("Supply a sequence of ingestion outcomes")
        items = tuple(self.items)
        if any(type(item) not in (IngestionSuccess, IngestionFailure) for item in items):
            raise TypeError("Supply typed ingestion outcomes")
        object.__setattr__(self, "items", items)

    @property
    def successes(self) -> tuple[IngestionSuccess, ...]:
        """Return only accepted results in their original order."""
        return tuple(item for item in self.items if isinstance(item, IngestionSuccess))

    @property
    def failures(self) -> tuple[IngestionFailure, ...]:
        """Return the per-input issues in their original order."""
        return tuple(item for item in self.items if isinstance(item, IngestionFailure))

    @property
    def revisions(self) -> tuple[SourceRevision, ...]:
        """Return the exact accepted revisions."""
        return tuple(item.ingested_source.revision for item in self.successes)
