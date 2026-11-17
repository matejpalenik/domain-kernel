"""Explicit acquisition, processing, retention and persistence capabilities."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel._shared.application.persistence import Transaction

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from contextlib import AbstractAsyncContextManager

    from domain_kernel._shared.domain.audit import Artifact
    from domain_kernel.configuration import SourceSelectionLimits
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.contracts import Page
    from domain_kernel.shared.identifiers.content_hash import ContentHash
    from domain_kernel.shared.identifiers.page_cursor import PageCursor
    from domain_kernel.sources.application.contracts import (
        FileDescriptor,
        ReaderLocation,
        SourceEntry,
    )
    from domain_kernel.sources.domain.identifiers.source_id import SourceId
    from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
    from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
    from domain_kernel.sources.domain.models import (
        FileOrigin,
        IngestedSource,
        OriginalWriteIntent,
        ProcessingLimits,
        Source,
        SourceProfile,
        SourceRevision,
    )


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
    ) -> Iterator[ParsedChunk]:
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
    async def profile(self, *, revision: SourceRevision) -> SourceProfile | None:
        """Read recorded processing metadata of this exact revision."""

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
class SourceTransaction(Transaction, Protocol, metaclass=ABCMeta):
    """Source storage joined to the operation's audit and replay resources."""

    @property
    @abstractmethod
    def sources(self) -> SourceRepository:
        """Return the transaction-bound source repository."""
