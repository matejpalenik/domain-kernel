"""Explicit acquisition, processing, retention and persistence capabilities."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, final, override, runtime_checkable

from domain_kernel.shared.application.protocols.transaction import Transaction
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from contextlib import AbstractAsyncContextManager
    from io import BytesIO

    from domain_kernel.configuration import SourceSelectionLimits
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor
    from domain_kernel.shared.domain.entities.artifact import Artifact
    from domain_kernel.shared.identifiers.content_hash import ContentHash
    from domain_kernel.sources.application.contracts import (
        FileDescriptor,
        ReaderLocation,
        SourceEntry,
    )
    from domain_kernel.sources.domain.coverage import CoverageUnit
    from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
    from domain_kernel.sources.domain.identifiers.source_id import SourceId
    from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
    from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
    from domain_kernel.sources.domain.models import (
        Evidence,
        FileOrigin,
        IngestedSource,
        OriginalWriteIntent,
        ProcessingLimits,
        ProcessingRecord,
        RetainedDocument,
        RetainedExcerpt,
        Source,
        SourceProfile,
        SourceRevision,
    )
    from domain_kernel.sources.domain.parsed import (
        ParsedPayload,
        ParsedSourceOrigin,
        ParsedTable,
        ParsedText,
    )
    from domain_kernel.sources.domain.statements import StatementPayload


class SeekableBytes(Protocol, metaclass=ABCMeta):
    """Keyword-only access to a bounded captured buffer."""

    @abstractmethod
    def read(self, *, size: int = -1) -> bytes:
        """Read at most the requested bytes from the current position."""

    @abstractmethod
    def seek(self, *, offset: int, whence: int = 0) -> int:
        """Seek within the captured buffer."""

    @abstractmethod
    def tell(self) -> int:
        """Return the current byte position."""


@final
class SourceBuffer(SeekableBytes):
    """Adapt an owned byte stream to the source parser port."""

    def __init__(self, *, data: BytesIO) -> None:
        """Keep access to a stream owned by the acquisition context."""
        self._data = data

    @override
    def read(self, *, size: int = -1) -> bytes:
        """Read from the captured buffer."""
        return self._data.read(size)

    @override
    def seek(self, *, offset: int, whence: int = 0) -> int:
        """Seek within the captured buffer."""
        return self._data.seek(offset, whence)

    @override
    def tell(self) -> int:
        """Report the captured buffer position."""
        return self._data.tell()


@dataclass(frozen=True, kw_only=True)
class AcquiredSource:
    """The opened buffer and the provider's verified acquisition metadata."""

    stream: SeekableBytes
    origin: FileOrigin
    byte_length: int
    content_hash: ContentHash


@runtime_checkable
class SourceReader(Protocol, metaclass=ABCMeta):
    """Acquire and enumerate under one explicitly bound provider scope."""

    @property
    @abstractmethod
    def provider_scope(self) -> str:
        """Return a stable, credential-free identifier for this configured binding."""

    @abstractmethod
    def open(
        self,
        *,
        location: ReaderLocation,
        limits: ProcessingLimits,
        expected: SourceRevision | None = None,
        expected_entry: SourceEntry | None = None,
    ) -> AbstractAsyncContextManager[AcquiredSource]:
        """Open the exact requested file as a bounded buffer."""

    @abstractmethod
    async def list_children(
        self,
        *,
        location: ReaderLocation,
        limits: SourceSelectionLimits,
        limit: int = 100,
        cursor: PageCursor | None = None,
    ) -> Page[SourceEntry]:
        """List immediate children using a query-bound cursor."""


@dataclass(frozen=True, kw_only=True)
class ParsedChunk:
    """One bounded host parser result with a section and optional page locator."""

    text: str
    section: str | None = None
    page: int | None = None


@runtime_checkable
class FormatParser(Protocol, metaclass=ABCMeta):
    """Host-supplied bounded format processing over explicitly acquired bytes."""

    @property
    @abstractmethod
    def parser_id(self) -> str:
        """Return the exact processing implementation identity."""

    @property
    @abstractmethod
    def parser_version(self) -> str:
        """Return the version used by subsequent reproducibility checks."""

    @abstractmethod
    def parse(
        self,
        *,
        content: AcquiredSource,
        descriptor: FileDescriptor,
        limits: ProcessingLimits,
    ) -> Iterator[ParsedChunk | ParsedTable | ParsedText | CoverageUnit]:
        """Stream normalized chunks without filesystem or network access."""


@runtime_checkable
class OriginalStore(Protocol, metaclass=ABCMeta):
    """Write an immutable verified artifact under one configured binding."""

    @property
    @abstractmethod
    def provider_scope(self) -> str:
        """Return a stable credential-free identifier for the bound store."""

    @abstractmethod
    async def verify(
        self,
        *,
        project_id: ProjectId,
        key: str,
        digest: ContentHash,
        byte_length: int,
    ) -> Artifact | None:
        """Verify a previously requested immutable artifact, or report its absence."""

    @abstractmethod
    async def put(
        self,
        *,
        project_id: ProjectId,
        key: str,
        content: bytes,
        digest: ContentHash,
    ) -> Artifact:
        """Create or verify an existing artifact with the exact same stable key and hash."""


@runtime_checkable
class ReadableOriginalStore(Protocol):
    """Optional exact original retrieval from an immutable destination."""

    async def read_original(
        self,
        *,
        key: str,
        revision: SourceRevision,
        max_bytes: int,
    ) -> bytes | None:
        """Load a bounded exact archived original, or report its absence."""
        ...


class SourceRepository(Protocol, metaclass=ABCMeta):
    """Persist immutable source revisions and guarded operation results."""

    @abstractmethod
    async def get(self, *, project_id: ProjectId, source_id: SourceId) -> Source:
        """Read a scoped source by its nominal identity."""

    @abstractmethod
    async def find_by_name(self, *, project_id: ProjectId, name: str) -> Source | None:
        """Read a scoped source by its lookup name."""

    @abstractmethod
    async def save(self, *, source: Source, expected_version: int | None) -> None:
        """Create a unique source or advance its inspected version."""

    @abstractmethod
    async def list(
        self,
        *,
        project_id: ProjectId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Source]:
        """Page through one project's exact sources."""

    @abstractmethod
    async def revision(
        self,
        *,
        project_id: ProjectId,
        source_id: SourceId,
        revision_id: SourceRevisionId,
    ) -> SourceRevision | None:
        """Read one exact immutable revision if it exists."""

    @abstractmethod
    async def add_revision(self, *, revision: SourceRevision) -> None:
        """Retain the first verified metadata record for an exact digest."""

    @abstractmethod
    async def list_revisions(
        self,
        *,
        project_id: ProjectId,
        source_id: SourceId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[SourceRevision]:
        """Page through immutable revisions in accepted order."""

    @abstractmethod
    async def add_result(
        self,
        *,
        project_id: ProjectId,
        key: str,
        result: IngestedSource,
        profile: SourceProfile | None,
    ) -> None:
        """Retain an exact completed ingestion result for deterministic replay."""

    @abstractmethod
    async def profile(
        self, *, revision: SourceRevision, processing_fingerprint: str | None = None
    ) -> SourceProfile | None:
        """Read the latest or explicitly selected processing profile for the revision."""

    @abstractmethod
    async def result(self, *, project_id: ProjectId, key: str) -> IngestedSource:
        """Reload a completed ingestion result."""

    @abstractmethod
    async def reserve_copy(
        self,
        *,
        project_id: ProjectId,
        key: str,
        intent: OriginalWriteIntent,
    ) -> None:
        """Persist the exact original and destination before writing external bytes."""

    @abstractmethod
    async def copy_intent(self, *, project_id: ProjectId, key: str) -> OriginalWriteIntent | None:
        """Find a retained external-write intent for an unfinished invocation."""

    @abstractmethod
    async def add_manifest(
        self,
        *,
        project_id: ProjectId,
        identifier: SourceManifestId,
        content: bytes,
        entry_keys: Sequence[str],
    ) -> None:
        """Save one verified immutable selection and its acquisition guards."""

    @abstractmethod
    async def manifest(self, *, project_id: ProjectId, identifier: SourceManifestId) -> bytes:
        """Read the exact authorized selection's durable bytes."""

    @abstractmethod
    async def manifest_for_item(self, *, project_id: ProjectId, key: str) -> bytes | None:
        """Find the frozen selection guarding this generated child key."""


@runtime_checkable
class ParsedSourceResolver(Protocol, metaclass=ABCMeta):
    """Caller-owned access to an exact upstream normalized capture."""

    @abstractmethod
    def open(
        self,
        *,
        origin: ParsedSourceOrigin,
        limits: ProcessingLimits,
    ) -> AbstractAsyncContextManager[ParsedPayload]:
        """Open the requested exact authorized host payload."""


@dataclass(frozen=True, kw_only=True)
class ParsedSourceProvider:
    """Named binding for one caller-owned resolver."""

    name: str
    resolver: ParsedSourceResolver

    def __post_init__(self) -> None:
        """Validate the stable name without opening or copying the resolver."""
        TextValidation.require_text(value=self.name, field="Parsed source provider")
        if not callable(getattr(self.resolver, "open", None)):
            raise TypeError("Supply a caller-owned parsed source resolver")


@runtime_checkable
class ParsedSourceRepository(Protocol, metaclass=ABCMeta):
    """Retain citations and explicitly retained host payloads with their source revision."""

    @abstractmethod
    async def add_evidence(self, *, evidence: Evidence) -> None:
        """Write one exact citation in its own project."""

    @abstractmethod
    async def evidence(self, *, project_id: ProjectId, identity: EvidenceId) -> Evidence | None:
        """Retrieve an authorized citation by nominal identity."""

    @abstractmethod
    async def retain_payload(self, *, revision: SourceRevision, payload: ParsedPayload) -> None:
        """Store host payload only when derivative retention is enabled."""

    @abstractmethod
    async def payload(self, *, revision: SourceRevision) -> ParsedPayload | None:
        """Retrieve the exact retained payload, if any."""


@runtime_checkable
class CorpusRepository(Protocol, metaclass=ABCMeta):
    """Read the recorded citation inventory for exact source revisions."""

    @abstractmethod
    async def citations(self, *, revision: SourceRevision) -> tuple[Evidence, ...]:
        """Return citations from the current recorded processing of this revision."""


@runtime_checkable
class ExcerptRepository(Protocol, metaclass=ABCMeta):
    """Store excerpts only after explicit retention and verified acquisition."""

    @abstractmethod
    async def retain_excerpt(self, *, excerpt: RetainedExcerpt) -> None:
        """Persist a citation's exact bounded normalized content."""

    @abstractmethod
    async def excerpt(self, *, evidence: Evidence) -> RetainedExcerpt | None:
        """Retrieve a previously stored excerpt by its exact citation identity."""


@runtime_checkable
class StatementRepository(Protocol, metaclass=ABCMeta):
    """Persist explicit primary statement captures."""

    @abstractmethod
    async def retain_statement(
        self, *, revision: SourceRevision, payload: StatementPayload
    ) -> None:
        """Retain the statement as part of its source transaction."""

    @abstractmethod
    async def statement(self, *, revision: SourceRevision) -> StatementPayload | None:
        """Retrieve the recorded primary payload of one revision."""


@runtime_checkable
class DocumentRepository(Protocol, metaclass=ABCMeta):
    """Store explicitly retained normalized documents by exact processing capture."""

    @abstractmethod
    async def retain_document(self, *, document: RetainedDocument) -> None:
        """Write the normalized parts within the original ingestion transaction."""

    @abstractmethod
    async def document(self, *, processing: ProcessingRecord) -> RetainedDocument | None:
        """Retrieve the retained parts of the exact processing capture."""


@runtime_checkable
class SourceTransaction(Transaction, Protocol, metaclass=ABCMeta):
    """Source storage joined to the operation's audit and replay resources."""

    @property
    @abstractmethod
    def sources(self) -> SourceRepository:
        """Return the transaction-bound source repository."""
