"""Immutable project-scoped source identity and verified acquisition metadata."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.audit import Artifact
from domain_kernel.shared.domain.naming import require_lookup_name
from domain_kernel.shared.errors import ScopeMismatchError
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import (
    require_exact,
    require_text,
    snapshot_sequence,
)
from domain_kernel.sources.domain.coverage import CoverageStatus, CoverageUnit
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
from domain_kernel.sources.domain.parsed import (
    EvidenceLocator,
    ParsedGraph,
    ParsedSourceOrigin,
    ParsedTable,
    ParsedText,
    require_locator,
)
from domain_kernel.sources.domain.statements import StatementOrigin
from domain_kernel.sources.domain.tables import TableProfile

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.sources.domain.parsed import ParsedPart


@dataclass(frozen=True, kw_only=True)
class FileOrigin:
    """Provider metadata captured with the verified original bytes."""

    reader: str
    provider_scope: str
    location: str
    provider_version: str | None
    acquired_at: datetime
    kind: Literal["file"] = "file"

    def __post_init__(self) -> None:
        """Check bounded provenance fields independently of file contents."""
        require_text(value=self.reader, field="Reader name")
        require_text(value=self.provider_scope, field="Provider scope")
        require_text(value=self.location, field="Relative source path")
        if self.provider_version is not None:
            require_text(value=self.provider_version, field="Provider version")
        require_exact(value=self.acquired_at, expected=datetime, field="Acquisition time")
        if (
            self.acquired_at.utcoffset() is None
            or type(self.kind) is not str
            or self.kind != "file"
        ):
            raise ValueError("Use an attributed acquisition time and the file origin kind")


type Origin = FileOrigin | ParsedSourceOrigin | StatementOrigin


@dataclass(frozen=True, kw_only=True)
class SourceRevision:
    """The exact byte digest and first acquisition recorded under a source."""

    project_id: ProjectId
    source_id: SourceId
    revision_id: SourceRevisionId
    byte_length: int
    origin: Origin

    def __post_init__(self) -> None:
        """Require nominal identity, exact length and captured provenance."""
        require_exact(value=self.project_id, expected=ProjectId, field="Project ID")
        require_exact(value=self.source_id, expected=SourceId, field="Source ID")
        require_exact(value=self.revision_id, expected=SourceRevisionId, field="Revision ID")
        if type(self.origin) not in (FileOrigin, ParsedSourceOrigin, StatementOrigin):
            raise TypeError("Use the exact captured file or supplied source origin")
        require_exact(value=self.byte_length, expected=int, field="Source length")
        if self.byte_length < 0:
            raise ValueError("Source length must be nonnegative")


@dataclass(frozen=True, kw_only=True)
class Source:
    """Retained lookup names and a monotonic project-local revision counter."""

    id: SourceId
    project_id: ProjectId
    name: str
    display_name: str
    version: int

    def __post_init__(self) -> None:
        """Preserve the assigned identity and validated lookup name."""
        require_exact(value=self.id, expected=SourceId, field="Source ID")
        require_exact(value=self.project_id, expected=ProjectId, field="Project ID")
        require_lookup_name(name=self.name)
        require_text(value=self.display_name, field="Source display name")
        require_exact(value=self.version, expected=int, field="Source version")
        if self.version < 1:
            raise ValueError("Source versions must be positive")

    def register_revision(self, *, revision: SourceRevision) -> Source:
        """Advance the source after an exact new revision is accepted."""
        require_exact(value=revision, expected=SourceRevision, field="Source revision")
        if revision.project_id != self.project_id or revision.source_id != self.id:
            raise ScopeMismatchError
        return replace(self, version=self.version + 1)


@dataclass(frozen=True, kw_only=True)
class ProcessingLimits:
    """Bounds for one client's in-memory acquisition and processing."""

    max_source_bytes: int
    max_concurrent_sources: int
    max_expanded_bytes: int
    max_pages: int
    max_table_cells: int = 1_000_000
    max_tables: int = 128

    def __post_init__(self) -> None:
        """Require independent positive exact limits."""
        for title, value in (
            ("Raw bytes", self.max_source_bytes),
            ("Concurrent sources", self.max_concurrent_sources),
            ("Expanded bytes", self.max_expanded_bytes),
            ("Pages", self.max_pages),
            ("Table cells", self.max_table_cells),
            ("Tables", self.max_tables),
        ):
            require_exact(value=value, expected=int, field=title)
            if value < 1:
                raise ValueError("Set positive source processing limits")


@dataclass(frozen=True, kw_only=True)
class OriginalCopy:
    """An explicitly retained, hash-verified external artifact."""

    source: SourceRevision
    artifact: Artifact
    verified_hash: ContentHash
    copied_at: datetime

    def __post_init__(self) -> None:
        """Bind the copy to the exact source digest and owning project."""
        require_exact(value=self.source, expected=SourceRevision, field="Source revision")
        require_exact(value=self.artifact, expected=Artifact, field="Original artifact")
        require_exact(value=self.verified_hash, expected=ContentHash, field="Verified hash")
        require_exact(value=self.copied_at, expected=datetime, field="Copy time")
        if (
            not isinstance(self.source.origin, FileOrigin)
            or self.verified_hash.value != self.source.revision_id.value
            or self.verified_hash != self.artifact.content_hash
            or self.source.project_id != self.artifact.project_id
            or self.copied_at.utcoffset() is None
        ):
            raise ValueError("Retain the exact verified original with an attributed time zone")


@dataclass(frozen=True, kw_only=True)
class IngestedSource:
    """The immutable acquired revision and the outcome of its selected processing."""

    revision: SourceRevision
    processing_fingerprint: str
    retained_original: OriginalCopy | None = None
    evidence: Sequence[Evidence] = ()

    def __post_init__(self) -> None:
        """Bind retained content to the inspected source digest."""
        require_exact(value=self.revision, expected=SourceRevision, field="Source revision")
        require_text(value=self.processing_fingerprint, field="Processing fingerprint")
        if self.retained_original is not None:
            require_exact(
                value=self.retained_original, expected=OriginalCopy, field="Original copy"
            )
            if self.retained_original.source != self.revision:
                raise ValueError("Retain an original copy of this exact source revision")
        evidence = snapshot_sequence(items=self.evidence, item_type=Evidence, field="Evidence")
        if any(
            item.source != self.revision
            or item.processing.fingerprint != self.processing_fingerprint
            for item in evidence
        ):
            raise ValueError("Bind citations to the exact captured source and processing record")
        object.__setattr__(self, "evidence", evidence)

    @property
    def source_id(self) -> SourceId:
        """Return the existing source identity."""
        return self.revision.source_id

    @property
    def revision_id(self) -> SourceRevisionId:
        """Return the exact full-content acquisition digest."""
        return self.revision.revision_id


@dataclass(frozen=True, kw_only=True)
class OriginalWriteIntent:
    """The exact acquisition and destination made durable before external I/O."""

    source: Source
    ingestion: IngestedSource
    artifact: Artifact
    audit_id: AuditId
    profile: SourceProfile | None = None
    document: RetainedDocument | None = field(default=None, repr=False)
    excerpts: tuple[RetainedExcerpt, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        """Keep recovery bound to the original content and source identity."""
        require_exact(value=self.source, expected=Source, field="Source identity")
        require_exact(
            value=self.ingestion, expected=IngestedSource, field="Captured bytes metadata"
        )
        require_exact(value=self.artifact, expected=Artifact, field="Requested artifact")
        require_exact(value=self.audit_id, expected=AuditId, field="Copy audit ID")
        revision = self.ingestion.revision
        if self.profile is not None:
            require_exact(value=self.profile, expected=SourceProfile, field="Captured profile")
            if self.profile.source != revision:
                raise ValueError("Keep the profile of the exact original source revision")
        if self.document is not None and (
            self.document.source != revision
            or self.document.fingerprint != self.ingestion.processing_fingerprint
        ):
            raise ValueError("Keep the normalized document of the exact acquired revision")
        if any(excerpt.evidence not in self.ingestion.evidence for excerpt in self.excerpts):
            raise ValueError("Retain excerpts of citations issued by the original acquisition")
        if (
            not isinstance(revision.origin, FileOrigin)
            or self.ingestion.retained_original is not None
            or revision.source_id != self.source.id
            or revision.project_id != self.source.project_id
            or revision.project_id != self.artifact.project_id
            or revision.revision_id.value != self.artifact.content_hash.value
        ):
            raise ValueError("Bind a verified original and its immutable destination")


@dataclass(frozen=True, kw_only=True)
class ProcessingRecord:
    """Identity and configured implementation of one processing capture."""

    source: SourceRevision
    fingerprint: str
    parser_id: str
    parser_version: str
    provider_model_id: str | None = None
    parser_options: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Keep the exact processed revision and implementation values."""
        require_exact(value=self.source, expected=SourceRevision, field="Processed source")
        require_text(value=self.fingerprint, field="Processing fingerprint")
        require_text(value=self.parser_id, field="Parser ID")
        require_text(value=self.parser_version, field="Parser version")
        if self.provider_model_id is not None:
            require_text(value=self.provider_model_id, field="Processing model ID")
        if self.parser_options is not None:
            require_text(value=self.parser_options, field="Parser options")


@dataclass(frozen=True, kw_only=True)
class SourceProfile:
    """Detached processing metadata with the observed locations."""

    source: SourceRevision
    processing: ProcessingRecord
    page_count: int | None = None
    sections: Sequence[str] = ()
    issues: Sequence[Issue] = ()
    tables: Sequence[TableProfile] = ()
    coverage: Sequence[CoverageUnit] = ()

    def __post_init__(self) -> None:
        """Bind profile metadata to an exact capture and freeze the inventories."""
        require_exact(value=self.source, expected=SourceRevision, field="Profile source")
        require_exact(value=self.processing, expected=ProcessingRecord, field="Profile processing")
        if self.processing.source != self.source:
            raise ValueError("Profile the exact captured source revision")
        if self.page_count is not None:
            require_exact(value=self.page_count, expected=int, field="Observed pages")
            if self.page_count < 1:
                raise ValueError("Use a positive observed page count")
        for title, items, kind in (
            ("sections", self.sections, str),
            ("issues", self.issues, Issue),
            ("tables", self.tables, TableProfile),
            ("coverage", self.coverage, CoverageUnit),
        ):
            object.__setattr__(
                self, title, snapshot_sequence(items=items, item_type=kind, field=title)
            )
        if len({unit.locator for unit in self.coverage}) != len(self.coverage):
            raise ValueError("Account for each source unit once")

    @property
    def processed_units(self) -> int:
        """Count units that produced usable parsed content."""
        return sum(unit.status is CoverageStatus.PROCESSED for unit in self.coverage)

    @property
    def accounted_units(self) -> int:
        """Count selected units with a recorded disposition, including empty units."""
        return len(self.coverage)

    @property
    def outstanding_units(self) -> tuple[CoverageUnit, ...]:
        """Expose selected units that were neither processed nor confirmed empty."""
        return tuple(
            unit
            for unit in self.coverage
            if unit.status not in (CoverageStatus.PROCESSED, CoverageStatus.EMPTY)
        )


@dataclass(frozen=True, kw_only=True)
class Evidence:
    """A citation into one exact captured source with attributed processing."""

    id: EvidenceId
    source: SourceRevision
    locator: EvidenceLocator
    processing: ProcessingRecord

    def __post_init__(self) -> None:
        """Bind a nominal citation to the exact captured revision."""
        require_exact(value=self.id, expected=EvidenceId, field="Evidence ID")
        require_exact(value=self.source, expected=SourceRevision, field="Evidence source")
        require_exact(value=self.processing, expected=ProcessingRecord, field="Evidence processing")
        require_locator(locator=self.locator)
        if self.processing.source != self.source:
            raise ValueError("Cite the exact processed source revision")


@dataclass(frozen=True, kw_only=True)
class EvidenceContent:
    """Explicitly resolved content at the citation's verified locator."""

    evidence: Evidence
    excerpt: str = field(repr=False)
    origin: Origin
    part: ParsedPart = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class RetainedDocument:
    """Normalized file content retained under a specific parser fingerprint."""

    source: SourceRevision
    fingerprint: str
    parts: tuple[ParsedText | ParsedTable, ...] = field(repr=False)

    def __post_init__(self) -> None:
        """Bind explicitly retained content to the recorded file revision."""
        require_exact(value=self.source, expected=SourceRevision, field="Retained document source")
        require_text(value=self.fingerprint, field="Document processing fingerprint")
        if not isinstance(self.source.origin, FileOrigin):
            raise TypeError("Retain normalized content from a file revision")
        if (
            type(self.parts) is not tuple
            or not self.parts
            or any(type(part) not in (ParsedText, ParsedTable) for part in self.parts)
        ):
            raise TypeError("Retain exact normalized document parts")


@dataclass(frozen=True, kw_only=True)
class RetainedExcerpt:
    """A separately retained excerpt of an exact recorded citation."""

    evidence: Evidence
    part: ParsedPart = field(repr=False)

    def __post_init__(self) -> None:
        """Bind the normalized content to the original citation."""
        require_exact(value=self.evidence, expected=Evidence, field="Excerpt citation")
        if type(self.part) not in (ParsedText, ParsedTable, ParsedGraph):
            raise TypeError("Retain exact normalized evidence content")
        if self.part.locator != self.evidence.locator:
            raise ValueError("Retain the excerpt of the exact cited locator")
