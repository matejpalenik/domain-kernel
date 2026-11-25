"""Acquire verified source bytes outside transactions and commit detached results."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from io import BytesIO
from tarfile import TarError
from tarfile import open as open_tar
from types import MappingProxyType
from typing import TYPE_CHECKING, final
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from pydantic import TypeAdapter

from domain_kernel._shared.application.artifact_delivery import DeliveryRequest, deliver
from domain_kernel._shared.application.persistence import (
    Invocation,
    OperationOutcome,
    keep_work_leased,
)
from domain_kernel._shared.domain.audit import (
    Artifact,
    AuditAction,
    AuditOutcome,
    AuditRecord,
    AuditResource,
)
from domain_kernel._shared.domain.naming import require_lookup_name, resolve_names
from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.shared.errors import (
    IdempotencyConflictError,
    MissingCapabilityError,
    ResourceLimitError,
    ScopeMismatchError,
    SourceNotFoundError,
    SourceReadError,
    StaleStateError,
)
from domain_kernel.shared.hashing import JsonValue, canonical_json_bytes, hash_bytes, hash_json
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, require_text
from domain_kernel.sources.application.citations import recorded_citation
from domain_kernel.sources.application.contracts import (
    CSV,
    PDF,
    CopyTo,
    Document,
    Excel,
    FileDescriptor,
    Ontology,
    ParsedSource,
    ReaderLocation,
    Statement,
    Word,
    document_kind,
)
from domain_kernel.sources.application.file_parsing import parse_file, resolve_document, run_parser
from domain_kernel.sources.application.manifests import SourceManifest
from domain_kernel.sources.application.parsed_sources import (
    capture_excerpts,
    capture_host_payload,
    iter_excerpts,
    resolve_excerpt,
    resolve_host_content,
)
from domain_kernel.sources.application.ports import (
    AcquiredSource,
    CorpusRepository,
    DocumentRepository,
    ExcerptRepository,
    ParsedSourceRepository,
    ReadableOriginalStore,
    SourceBuffer,
    SourceTransaction,
    StatementRepository,
)
from domain_kernel.sources.application.statements import (
    attributed_payload,
    canonical_statement,
    capture_statement,
    resolve_statement,
)
from domain_kernel.sources.domain.coverage import CoverageStatus
from domain_kernel.sources.domain.document_formats import DocumentFormat
from domain_kernel.sources.domain.errors.evidence_unavailable_error import EvidenceUnavailableError
from domain_kernel.sources.domain.errors.source_already_exists_error import SourceAlreadyExistsError
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.errors.source_unavailable_error import SourceUnavailableError
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
from domain_kernel.sources.domain.models import (
    Evidence,
    EvidenceContent,
    FileOrigin,
    IngestedSource,
    OriginalCopy,
    OriginalWriteIntent,
    ProcessingRecord,
    RetainedDocument,
    RetainedExcerpt,
    Source,
    SourceProfile,
    SourceRevision,
)
from domain_kernel.sources.domain.parsed import ParsedPayload, ParsedSourceOrigin
from domain_kernel.sources.domain.parsed_codec import canonical_capture
from domain_kernel.sources.domain.statements import StatementOrigin, StatementPayload

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping, Sequence

    from domain_kernel._shared.application.persistence import Lease, Transaction, UnitOfWorkFactory
    from domain_kernel.configuration import SourceSelectionLimits
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.contracts import Page
    from domain_kernel.shared.identifiers.page_cursor import PageCursor
    from domain_kernel.sources.application.contracts import (
        SourceDescriptor,
        SourceEntry,
    )
    from domain_kernel.sources.application.file_parsing import FileParsing
    from domain_kernel.sources.application.ports import (
        FormatParser,
        OriginalStore,
        ParsedSourceResolver,
        SourceReader,
        SourceRepository,
    )
    from domain_kernel.sources.domain.models import ProcessingLimits


@dataclass(frozen=True, kw_only=True)
class CaptureRequest:
    """One exact source command before acquisition."""

    source: SourceDescriptor
    name: str | None = None
    display_name: str | None = None
    source_id: SourceId | None = None
    retain_original: CopyTo | None = None
    idempotency_key: str | None = None
    expected_entry: SourceEntry | None = None

    def file(self) -> FileDescriptor:
        """Select the explicitly typed file descriptor for file-only operations."""
        if isinstance(self.source, (ParsedSource, Statement)):
            raise TypeError("Use a captured file descriptor for this operation")
        return self.source


@dataclass(frozen=True, kw_only=True)
class AcquiredRevision:
    """The detached outcome of an exact file acquisition."""

    ingestion: IngestedSource
    profile: SourceProfile | None
    content: bytes | None = field(repr=False)
    document: RetainedDocument | None = None
    excerpts: tuple[RetainedExcerpt, ...] = ()


@final
class SourceRuntime:
    """Explicit host capabilities and one shared acquisition concurrency ceiling."""

    def __init__(  # noqa: PLR0913 - Independent configurable source boundaries.
        self,
        *,
        readers: Mapping[str, SourceReader],
        parsers: Mapping[str, FormatParser],
        stores: Mapping[str, OriginalStore],
        limits: ProcessingLimits,
        selection: SourceSelectionLimits,
        default_original_store: str | None,
        parsed_providers: Mapping[str, ParsedSourceResolver],
        retain_parsed: bool,
        retain_excerpts: bool = False,
    ) -> None:
        """Capture named capabilities for this client's project handles."""
        self.readers = MappingProxyType(dict(readers))
        self.parsers = MappingProxyType(dict(parsers))
        self.stores = MappingProxyType(dict(stores))
        self.limits = limits
        self.selection = selection
        self.default_original_store = default_original_store
        self.parsed_providers = MappingProxyType(dict(parsed_providers))
        self.retain_parsed = retain_parsed
        self.retain_excerpts = retain_excerpts
        self.gate = asyncio.Semaphore(value=limits.max_concurrent_sources)

    def parsed_resolver(self, *, provider: str) -> ParsedSourceResolver:
        """Locate the original caller-owned binding without opening the payload."""
        resolver = self.parsed_providers.get(provider)
        if resolver is None:
            raise MissingCapabilityError(message="Register the named host capture provider")
        return resolver

    def reader(self, *, name: str) -> SourceReader:
        """Select an explicitly configured reader."""
        reader = self.readers.get(name)
        if reader is None:
            raise MissingCapabilityError(message="Configure a source reader for the selected name")
        return reader


@asynccontextmanager
async def source_transaction(
    *,
    resources: UnitOfWorkFactory[Transaction],
) -> AsyncGenerator[SourceTransaction]:
    """Acquire source metadata capabilities from one operation-local session."""
    async with resources() as transaction:
        if not isinstance(transaction, SourceTransaction):
            raise MissingCapabilityError(message="Configure durable source metadata persistence")
        yield transaction


def _source_intent(*, request: CaptureRequest) -> tuple[str | None, str | None]:
    if type(request.source) not in (
        PDF,
        CSV,
        Excel,
        Word,
        Document,
        Ontology,
        ParsedSource,
        Statement,
    ):
        raise TypeError("Select a supported typed source descriptor")
    if request.source_id is not None:
        require_exact(value=request.source_id, expected=SourceId, field="Source ID")
        return None, None
    return resolve_names(name=request.name, display_name=request.display_name)


def _original_key(*, project_id: ProjectId, digest: ContentHash) -> str:
    return f"sources/{project_id.value}/{digest.value.removeprefix('sha256:')}"


def _raw_bytes(*, acquired: AcquiredSource, max_bytes: int) -> bytes:
    _ = acquired.stream.seek(offset=0)
    content = acquired.stream.read(size=max_bytes + 1)
    if len(content) > max_bytes:
        raise ResourceLimitError
    if len(content) != acquired.byte_length or hash_bytes(content=content) != acquired.content_hash:
        raise SourceRevisionMismatchError
    _ = acquired.stream.seek(offset=0)
    return content


def _verify_format(*, source: FileDescriptor, content: bytes, limits: ProcessingLimits) -> None:
    kind = document_kind(descriptor=source)
    if kind is DocumentFormat.PDF:
        if not content.startswith(b"%PDF-"):
            raise SourceReadError(message="Supply the original bytes of a PDF file.")
        if (
            isinstance(source, PDF)
            and source.pages is not None
            and max(source.pages) > limits.max_pages
        ):
            raise ResourceLimitError(message="Select PDF pages within the configured limit")

    if kind is DocumentFormat.METS_GBS:
        _verify_tar(content=content, limits=limits)
    if kind in {
        DocumentFormat.DOCX,
        DocumentFormat.XLSX,
        DocumentFormat.PPTX,
        DocumentFormat.ODT,
        DocumentFormat.ODS,
        DocumentFormat.ODP,
        DocumentFormat.EPUB,
        DocumentFormat.DCLX,
        DocumentFormat.IWORK_PAGES,
        DocumentFormat.IWORK_NUMBERS,
        DocumentFormat.IWORK_KEYNOTE,
    }:
        try:
            with ZipFile(BytesIO(content)) as archive:
                members = archive.infolist()
                expanded = sum(item.file_size for item in members)
        except BadZipFile:
            raise SourceReadError(message="Supply a valid document container.") from None
        if expanded > limits.max_expanded_bytes or len(members) > _ARCHIVE_MEMBER_LIMIT:
            raise ResourceLimitError(message="Use a document container within the archive limits.")


_ARCHIVE_MEMBER_LIMIT = 10_000


def _verify_tar(*, content: bytes, limits: ProcessingLimits) -> None:
    expanded = 0
    try:
        with open_tar(fileobj=BytesIO(content), mode="r|gz") as archive:
            for position, member in enumerate(archive, start=1):
                if not (member.isfile() or member.isdir()):
                    raise SourceReadError(message="Use a document archive without links.")
                expanded += member.size
                if expanded > limits.max_expanded_bytes or position > _ARCHIVE_MEMBER_LIMIT:
                    raise ResourceLimitError(
                        message="Use a document container within the archive limits."
                    )
    except (TarError, OSError, EOFError):
        raise SourceReadError(message="Supply a valid METS/GBS archive.") from None


_FILE_DESCRIPTOR = TypeAdapter[FileDescriptor](FileDescriptor)
_PARSER_OPTIONS = TypeAdapter[dict[str, JsonValue]](dict[str, JsonValue])


def _format_fingerprint(*, descriptor: FileDescriptor, implementation: tuple[str, str]) -> str:
    return hash_json(
        value=(
            "source-processing-v1",
            descriptor.model_dump_json(exclude={"path", "location", "expected_hash"}),
            implementation,
        )
    ).value


def _audit_capture(
    *,
    invocation: Invocation,
    source: Source,
    previous: Source | None,
    result: IngestedSource,
) -> AuditRecord:
    return AuditRecord(
        id=AuditId(value=uuid4().hex),
        project_id=invocation.project_id,
        model_id=None,
        action=AuditAction(invocation.operation),
        outcome=AuditOutcome.SUCCEEDED,
        actor=invocation.actor,
        recorded_at=datetime.now(tz=UTC),
        before=() if previous is None else (_source_resource(source=previous),),
        after=(
            _source_resource(source=source),
            AuditResource(
                resource_id=result.revision_id,
                revision=None,
                content_hash=hash_json(value=record_value(value=result.revision)),
            ),
            *(() if result.retained_original is None else (result.retained_original.artifact,)),
        ),
    )


def _source_resource(*, source: Source) -> AuditResource:
    return AuditResource(
        resource_id=source.id,
        revision=source.version,
        content_hash=hash_json(value=record_value(value=source)),
    )


_SOURCE_HEARTBEAT_SECONDS = 20


@dataclass(kw_only=True)
class _FileClaims:
    """Current fenced leases and the local lock used during journal setup."""

    items: tuple[tuple[Invocation, Lease], ...]
    mutation: asyncio.Lock = field(default_factory=asyncio.Lock)


@final
class Sources:
    """Project-scoped source operations over explicit provider and transaction capabilities."""

    def __init__(
        self,
        *,
        project_id: ProjectId,
        resources: UnitOfWorkFactory[Transaction],
        runtime: SourceRuntime,
    ) -> None:
        """Bind the same runtime limits and readers to this project."""
        self._project_id = project_id
        self._resources = resources
        self._runtime = runtime

    def _invocation(
        self,
        *,
        actor: str,
        request: CaptureRequest,
        reader: SourceReader,
        store_name: str | None,
        store_binding: str | None,
    ) -> Invocation:
        name, display_name = _source_intent(request=request)
        location = request.file().resolved_location()
        entry = request.expected_entry
        return Invocation.resolve(
            project_id=self._project_id,
            model_id=None,
            operation="ingest_source" if request.source_id is None else "ingest_source_revision",
            actor=actor,
            key=request.idempotency_key,
            intent=(
                name,
                display_name,
                None if request.source_id is None else request.source_id.value,
                location.reader,
                location.path,
                request.source.model_dump_json(exclude={"path", "location"}),
                reader.provider_scope,
                store_name,
                store_binding,
                None if entry is None else (entry.provider_item_id, entry.provider_version),
            ),
        )

    async def _claim(
        self,
        *,
        invocations: Sequence[Invocation],
        transaction: SourceTransaction,
    ) -> tuple[tuple[Invocation, Lease], ...] | IngestedSource:
        pending: list[tuple[Invocation, Lease]] = []
        recorded: OperationOutcome | None = None
        owner = uuid4().hex
        for invocation in dict.fromkeys(invocations):
            result = await transaction.operations.claim(invocation=invocation, owner=owner)
            if isinstance(result, OperationOutcome):
                if result.resource_kind != "source_ingestion" or (
                    recorded is not None and result != recorded
                ):
                    raise IdempotencyConflictError
                recorded = result
            else:
                pending.append((invocation, result))
        if recorded is None:
            return tuple(pending)
        for invocation, lease in pending:
            await transaction.operations.complete(
                invocation=invocation,
                lease=lease,
                outcome=recorded,
            )
        return await transaction.sources.result(
            project_id=self._project_id, key=recorded.resource_id
        )

    async def _capture_source(
        self,
        *,
        request: CaptureRequest,
        transaction: SourceTransaction,
    ) -> Source:
        if request.source_id is not None:
            return await transaction.sources.get(
                project_id=self._project_id,
                source_id=request.source_id,
            )
        name, label = resolve_names(name=request.name, display_name=request.display_name)
        if await transaction.sources.find_by_name(project_id=self._project_id, name=name):
            raise SourceAlreadyExistsError
        return Source(
            id=SourceId(value=uuid4().hex),
            project_id=self._project_id,
            name=name,
            display_name=label,
            version=1,
        )

    async def _guard_manifest_item(
        self,
        *,
        request: CaptureRequest,
        actor: str,
        transaction: SourceTransaction,
    ) -> CaptureRequest:
        key = request.idempotency_key
        if key is None or request.expected_entry is not None:
            return request
        content = await transaction.sources.manifest_for_item(project_id=self._project_id, key=key)
        if content is None:
            return request
        manifest = SourceManifest.model_validate_json(content)
        for item in manifest.items:
            expected = item.input
            if expected is None or expected.idempotency_key != key:
                continue
            if (
                manifest.actor != actor
                or request.source_id is not None
                or expected.retain_original != request.retain_original
                or resolve_names(name=expected.name, display_name=expected.display_name)
                != _source_intent(request=request)
                or isinstance(expected.source, (ParsedSource, Statement))
                or expected.source.resolved_location() != request.file().resolved_location()
                or expected.source.model_dump_json(exclude={"path", "location"})
                != request.source.model_dump_json(exclude={"path", "location"})
            ):
                raise IdempotencyConflictError
            return replace(request, expected_entry=item.file)
        raise StaleStateError(message="Reload the frozen selection containing this file key.")

    async def ingest(
        self,
        *,
        actor: str,
        request: CaptureRequest,
        aliases: Sequence[CaptureRequest] = (),
    ) -> IngestedSource:
        """Replay before opening a file and commit the outcome under every equivalent key."""
        if isinstance(request.source, (ParsedSource, Statement)):
            return await self._ingest_payload(actor=actor, request=request, aliases=aliases)
        reader = self._runtime.reader(name=request.file().resolved_location().reader)
        store_name = (
            self._runtime.default_original_store
            if request.retain_original is None
            else request.retain_original.store
        )
        destination = None if store_name is None else self._runtime.stores.get(store_name)
        async with source_transaction(resources=self._resources) as transaction:
            async with transaction.begin():
                guarded = [
                    await self._guard_manifest_item(
                        request=item, actor=actor, transaction=transaction
                    )
                    for item in (request, *aliases)
                ]
                request = guarded[0]
                invocations = tuple(
                    self._invocation(
                        actor=actor,
                        request=item,
                        reader=reader,
                        store_name=store_name,
                        store_binding=None if destination is None else destination.provider_scope,
                    )
                    for item in guarded
                )
            # Finish immutable manifest reads before acquiring the writer reservation.
            async with transaction.begin():
                claims = await self._claim(invocations=invocations, transaction=transaction)
                if isinstance(claims, IngestedSource):
                    return claims
                intent = await self._copy_intent(claims=claims, transaction=transaction)
                source = (
                    await self._capture_source(request=request, transaction=transaction)
                    if intent is None
                    else intent.source
                )
                if store_name is not None and destination is None:
                    raise MissingCapabilityError(
                        message="Configure the selected immutable original store",
                    )
            active = _FileClaims(items=claims)

            async def renew() -> None:
                async with active.mutation:
                    async with transaction.begin():
                        renewed = tuple(
                            [
                                (
                                    item,
                                    await transaction.operations.renew(
                                        invocation=item, lease=lease
                                    ),
                                )
                                for item, lease in active.items
                            ]
                        )
                    active.items = renewed

            try:
                acquired, artifact, intent = await keep_work_leased(
                    work=self._acquire_original(
                        request=request,
                        source=source,
                        reader=reader,
                        destination=destination,
                        intent=intent,
                        active=active,
                        transaction=transaction,
                        store_name=store_name,
                    ),
                    renew=renew,
                    interval=_SOURCE_HEARTBEAT_SECONDS,
                )
                return await self._commit(
                    captured=acquired.ingestion,
                    profile=acquired.profile,
                    artifact=artifact,
                    source=source,
                    claims=active.items,
                    transaction=transaction,
                    intent=intent,
                    document=acquired.document,
                    excerpts=acquired.excerpts,
                )
            except BaseException:
                async with transaction.begin():
                    for invocation, lease in active.items:
                        with suppress(StaleStateError):
                            await transaction.operations.release(invocation=invocation, lease=lease)
                raise

    async def _acquire_original(  # noqa: PLR0913 - Preserve the exact capture and journal bindings.
        self,
        *,
        request: CaptureRequest,
        source: Source,
        reader: SourceReader,
        destination: OriginalStore | None,
        intent: OriginalWriteIntent | None,
        active: _FileClaims,
        transaction: SourceTransaction,
        store_name: str | None,
    ) -> tuple[AcquiredRevision, Artifact | None, OriginalWriteIntent | None]:
        async with self._runtime.gate:
            if intent is None or destination is None:
                acquired = await self._acquire(request=request, source=source, reader=reader)
            else:
                acquired = AcquiredRevision(
                    ingestion=intent.ingestion,
                    profile=intent.profile,
                    content=None,
                    document=intent.document,
                    excerpts=intent.excerpts,
                )
            if destination is None or store_name is None:
                return acquired, None, intent
            if intent is None:
                intent = self._requested_copy(
                    store_name=store_name, source=source, acquired=acquired
                )
                async with active.mutation:
                    active.items = await self._reserve_copy(
                        claims=active.items, transaction=transaction, intent=intent
                    )
            artifact = await self._retain(
                destination=destination,
                intent=intent,
                provided=acquired.content,
                capture=request,
                reader=reader,
            )
        return acquired, artifact, intent

    def _capture_payload(
        self,
        *,
        source: SourceDescriptor,
        actor: str,
    ) -> tuple[ParsedPayload | StatementPayload, bytes]:
        limits = self._runtime.limits
        if isinstance(source, Statement):
            statement = attributed_payload(statement=source, actor=actor)
            return statement, canonical_statement(payload=statement, limits=limits)
        if isinstance(source, ParsedSource):
            payload = source.capture()
            _ = self._runtime.parsed_resolver(provider=payload.origin.provider)
            return payload, canonical_capture(payload=payload, limits=limits)
        raise TypeError("Supply a typed statement or host capture")

    async def _ingest_payload(
        self,
        *,
        actor: str,
        request: CaptureRequest,
        aliases: Sequence[CaptureRequest],
    ) -> IngestedSource:
        if any(item.retain_original is not None for item in (request, *aliases)):
            raise SourceUnavailableError
        payload, canonical = self._capture_payload(source=request.source, actor=actor)
        digest = hash_bytes(content=canonical)
        invocations = tuple(
            Invocation.resolve(
                project_id=self._project_id,
                model_id=None,
                operation="ingest_source" if item.source_id is None else "ingest_source_revision",
                actor=actor,
                key=item.idempotency_key,
                intent=(
                    request.source.format,
                    _source_intent(request=item),
                    digest.value,
                    None if item.source_id is None else item.source_id.value,
                ),
            )
            for item in (request, *aliases)
        )
        async with source_transaction(resources=self._resources) as transaction:
            async with transaction.begin():
                if not isinstance(transaction.sources, ParsedSourceRepository):
                    raise MissingCapabilityError(message="Configure supplied capture persistence")
                if isinstance(payload, StatementPayload) and not isinstance(
                    transaction.sources, StatementRepository
                ):
                    raise MissingCapabilityError(message="Configure statement capture persistence")
                for invocation in invocations:
                    if (
                        await transaction.sources.manifest_for_item(
                            project_id=self._project_id,
                            key=invocation.idempotency_key,
                        )
                        is not None
                    ):
                        raise IdempotencyConflictError
            async with transaction.begin():
                claims = await self._claim(invocations=invocations, transaction=transaction)
                if isinstance(claims, IngestedSource):
                    return claims
                source = await self._capture_source(request=request, transaction=transaction)
            try:
                captured = (
                    capture_statement(source=source, payload=payload, canonical=canonical)
                    if isinstance(payload, StatementPayload)
                    else capture_host_payload(source=source, payload=payload, canonical=canonical)
                )
                excerpts = (
                    capture_excerpts(evidence=captured.evidence, parts=payload.parts)
                    if isinstance(payload, ParsedPayload) and self._runtime.retain_excerpts
                    else ()
                )
                return await self._commit(
                    captured=captured,
                    profile=None,
                    artifact=None,
                    source=source,
                    transaction=transaction,
                    claims=claims,
                    intent=None,
                    payload=payload
                    if isinstance(payload, StatementPayload) or self._runtime.retain_parsed
                    else None,
                    excerpts=excerpts,
                )
            except BaseException:
                async with transaction.begin():
                    for invocation, lease in claims:
                        with suppress(StaleStateError):
                            await transaction.operations.release(invocation=invocation, lease=lease)
                raise

    async def _discovery_citations(self, *, revision: SourceRevision) -> tuple[Evidence, ...]:
        """Load a source capture that has no deferred units."""
        require_exact(value=revision, expected=SourceRevision, field="Source revision")
        if revision.project_id != self._project_id:
            raise ScopeMismatchError
        async with (
            source_transaction(resources=self._resources) as transaction,
            transaction.begin(),
        ):
            repository = transaction.sources
            inspected = await repository.revision(
                project_id=self._project_id,
                source_id=revision.source_id,
                revision_id=revision.revision_id,
            )
            if inspected != revision:
                raise SourceRevisionMismatchError
            if not isinstance(repository, CorpusRepository):
                raise MissingCapabilityError(message="Configure source citation inventory access")
            citations = await repository.citations(revision=revision)
            profile = await repository.profile(
                revision=revision,
                processing_fingerprint=citations[0].processing.fingerprint if citations else None,
            )
            if profile is not None and any(
                unit.status is CoverageStatus.DEFERRED for unit in profile.coverage
            ):
                raise ResourceLimitError(
                    message=(
                        "Source coverage has deferred units. "
                        "Reprocess the pinned original and resume discovery."
                    )
                )
            return citations

    async def get_evidence(self, *, evidence: Evidence) -> EvidenceContent:
        """Resolve the recorded citation against its exact retained or upstream content."""
        require_exact(value=evidence, expected=Evidence, field="Evidence")
        if evidence.source.project_id != self._project_id:
            raise ScopeMismatchError
        recorded, cached = await self._read_citation(evidence=evidence)
        limits = self._runtime.limits
        if isinstance(cached, RetainedExcerpt):
            return resolve_excerpt(evidence=recorded, excerpt=cached, limits=limits)
        if isinstance(cached, StatementPayload):
            return resolve_statement(evidence=recorded, payload=cached, limits=limits)
        if isinstance(cached, ParsedPayload):
            return resolve_host_content(evidence=recorded, payload=cached, limits=limits)
        if isinstance(cached, RetainedDocument):
            return resolve_document(evidence=recorded, document=cached, limits=limits)
        origin = recorded.source.origin
        if isinstance(origin, FileOrigin):
            parsed = await self._parse_file_evidence(evidence=recorded)
            return parsed.resolve(evidence=recorded)
        if not isinstance(origin, ParsedSourceOrigin):
            raise EvidenceUnavailableError
        resolver = self._runtime.parsed_resolver(provider=origin.provider)
        try:
            async with self._runtime.gate, resolver.open(origin=origin, limits=limits) as resolved:
                return resolve_host_content(evidence=recorded, payload=resolved, limits=limits)
        except (OSError, SourceUnavailableError):
            raise EvidenceUnavailableError from None

    async def iter_evidence(
        self, *, revision: SourceRevision, pinned: Sequence[Evidence] | None = None
    ) -> AsyncGenerator[EvidenceContent]:
        """Resolve the selected capture once across all citations in a discovery operation."""
        citations = await self._discovery_citations(revision=revision) if pinned is None else pinned
        if not citations:
            return
        if any(citation.source != revision for citation in citations):
            raise SourceRevisionMismatchError
        first = citations[0]
        if isinstance(revision.origin, FileOrigin) and all(
            item.source == revision and item.processing == first.processing for item in citations
        ):
            _, cached = await self._read_citation(evidence=first)
            if isinstance(cached, RetainedDocument):
                if cached.source != revision or cached.fingerprint != first.processing.fingerprint:
                    raise SourceRevisionMismatchError
                parts = cached.parts
            elif cached is None:
                parsed = await self._parse_file_evidence(evidence=first)
                parts = (*parsed.texts, *parsed.tables)
            else:
                parts = ()
            if parts:
                for excerpt in iter_excerpts(evidence=citations, parts=parts):
                    yield resolve_excerpt(
                        evidence=excerpt.evidence,
                        excerpt=excerpt,
                        limits=self._runtime.limits,
                    )
                return
        for citation in citations:
            yield await self.get_evidence(evidence=citation)

    async def _read_citation(
        self,
        *,
        evidence: Evidence,
    ) -> tuple[
        Evidence, ParsedPayload | StatementPayload | RetainedDocument | RetainedExcerpt | None
    ]:
        async with (
            source_transaction(resources=self._resources) as transaction,
            transaction.begin(),
        ):
            recorded = await recorded_citation(
                repository=transaction.sources,
                project_id=self._project_id,
                expected=evidence,
            )
            if isinstance(transaction.sources, ExcerptRepository):
                excerpt = await transaction.sources.excerpt(evidence=recorded)
                if excerpt is not None:
                    return recorded, excerpt
            origin = recorded.source.origin
            if isinstance(origin, FileOrigin):
                document = (
                    await transaction.sources.document(processing=recorded.processing)
                    if isinstance(transaction.sources, DocumentRepository)
                    else None
                )
                return recorded, document
            if isinstance(origin, StatementOrigin):
                if not isinstance(transaction.sources, StatementRepository):
                    raise MissingCapabilityError(message="Configure statement capture persistence")
                return recorded, await transaction.sources.statement(revision=recorded.source)
            if not isinstance(transaction.sources, ParsedSourceRepository):
                raise MissingCapabilityError(message="Configure parsed source persistence")
            return recorded, await transaction.sources.payload(revision=recorded.source)

    async def _parse_file_evidence(self, *, evidence: Evidence) -> FileParsing:
        try:
            return await self._read_file_capture(evidence=evidence)
        except SourceNotFoundError:
            raise EvidenceUnavailableError from None

    async def _read_file_capture(self, *, evidence: Evidence) -> FileParsing:
        processing = evidence.processing
        origin = evidence.source.origin
        if processing.parser_options is None or not isinstance(origin, FileOrigin):
            raise EvidenceUnavailableError
        payload = _PARSER_OPTIONS.validate_json(processing.parser_options)
        payload["location"] = {"reader": origin.reader, "path": origin.location}
        descriptor = _FILE_DESCRIPTOR.validate_json(canonical_json_bytes(value=payload))
        parser = self._runtime.parsers.get(descriptor.format)
        if parser is None or (parser.parser_id, parser.parser_version) != (
            processing.parser_id,
            processing.parser_version,
        ):
            raise MissingCapabilityError(
                message="Configure the parser version recorded by this citation."
            )
        revision = evidence.source
        digest = ContentHash(value=revision.revision_id.value)
        async with AsyncExitStack() as stack:
            try:
                acquired = await stack.enter_async_context(
                    self._open_original(revision=revision, digest=digest),
                )
            except (SourceNotFoundError, SourceRevisionMismatchError, MissingCapabilityError):
                acquired = await stack.enter_async_context(
                    self._open_retained_original(revision=revision, origin=origin, digest=digest),
                )
                if acquired is None:
                    raise
            limits = self._runtime.limits
            content = _raw_bytes(acquired=acquired, max_bytes=limits.max_source_bytes)
            _verify_format(source=descriptor, content=content, limits=limits)
            parsed = await run_parser(
                parse=lambda: parse_file(
                    parser=parser,
                    acquired=acquired,
                    descriptor=descriptor,
                    limits=limits,
                    reparse=True,
                ),
            )
            fingerprint = _format_fingerprint(
                descriptor=descriptor,
                implementation=(processing.parser_id, processing.parser_version),
            )
            if parsed.capture_fingerprint(configuration_fingerprint=fingerprint) != (
                processing.fingerprint
            ):
                raise EvidenceUnavailableError
            return parsed

    @asynccontextmanager
    async def _open_retained_original(
        self,
        *,
        revision: SourceRevision,
        origin: FileOrigin,
        digest: ContentHash,
    ) -> AsyncGenerator[AcquiredSource | None]:
        key = _original_key(project_id=revision.project_id, digest=digest)
        async with self._runtime.gate:
            for store in self._runtime.stores.values():
                if not isinstance(store, ReadableOriginalStore):
                    continue
                content = await store.read_original(
                    key=key,
                    revision=revision,
                    max_bytes=self._runtime.limits.max_source_bytes,
                )
                if content is not None:
                    with BytesIO(content) as stream:
                        yield AcquiredSource(
                            stream=SourceBuffer(data=stream),
                            origin=origin,
                            byte_length=revision.byte_length,
                            content_hash=digest,
                        )
                    return
            yield None

    @staticmethod
    def _copy_key(*, invocation: Invocation) -> str:
        return hash_json(value=(invocation.operation, invocation.idempotency_key)).value

    async def _copy_intent(
        self,
        *,
        claims: Sequence[tuple[Invocation, Lease]],
        transaction: SourceTransaction,
    ) -> OriginalWriteIntent | None:
        found: OriginalWriteIntent | None = None
        for invocation, _ in claims:
            observed = await transaction.sources.copy_intent(
                project_id=self._project_id,
                key=self._copy_key(invocation=invocation),
            )
            if observed is not None:
                if found is not None and found != observed:
                    raise IdempotencyConflictError
                found = observed
        return found

    def _requested_copy(
        self,
        *,
        store_name: str,
        source: Source,
        acquired: AcquiredRevision,
    ) -> OriginalWriteIntent:
        digest = ContentHash(value=acquired.ingestion.revision_id.value)
        key = _original_key(project_id=source.project_id, digest=digest)
        return OriginalWriteIntent(
            source=source,
            ingestion=acquired.ingestion,
            profile=acquired.profile,
            document=acquired.document,
            excerpts=acquired.excerpts,
            audit_id=AuditId(value=uuid4().hex),
            artifact=Artifact(
                project_id=source.project_id, store=store_name, key=key, content_hash=digest
            ),
        )

    async def _reserve_copy(
        self,
        *,
        claims: Sequence[tuple[Invocation, Lease]],
        transaction: SourceTransaction,
        intent: OriginalWriteIntent,
    ) -> tuple[tuple[Invocation, Lease], ...]:
        reserved: list[tuple[Invocation, Lease]] = []
        async with transaction.begin():
            for invocation, lease in claims:
                current = await transaction.operations.renew(invocation=invocation, lease=lease)
                reserved.append((invocation, current))
                await transaction.sources.reserve_copy(
                    project_id=self._project_id,
                    key=self._copy_key(invocation=invocation),
                    intent=intent,
                )
            invocation = claims[0][0]
            await transaction.audit.append(
                record=AuditRecord(
                    id=intent.audit_id,
                    project_id=self._project_id,
                    model_id=None,
                    action=AuditAction.COPY_SOURCE_ORIGINAL,
                    outcome=AuditOutcome.STARTED,
                    actor=invocation.actor,
                    recorded_at=datetime.now(tz=UTC),
                    before=(),
                    after=(),
                    requested_artifact=intent.artifact,
                ),
            )
        return tuple(reserved)

    async def _retain(
        self,
        *,
        destination: OriginalStore,
        intent: OriginalWriteIntent,
        provided: bytes | None,
        capture: CaptureRequest,
        reader: SourceReader,
    ) -> Artifact:
        expected = intent.artifact
        artifact = await destination.verify(
            project_id=self._project_id,
            key=expected.key,
            digest=expected.content_hash,
            byte_length=intent.ingestion.revision.byte_length,
        )
        if artifact is None:
            if provided is None:
                observed = await self._acquire(
                    request=capture,
                    source=intent.source,
                    reader=reader,
                    expected=intent.ingestion.revision,
                )
                if (
                    observed.ingestion.revision_id != intent.ingestion.revision_id
                    or observed.content is None
                ):
                    raise SourceRevisionMismatchError
                provided = observed.content
            artifact = await destination.put(
                project_id=self._project_id,
                key=expected.key,
                digest=expected.content_hash,
                content=provided,
            )
        if (
            artifact.project_id != expected.project_id
            or artifact.store != expected.store
            or artifact.key != expected.key
            or artifact.content_hash != expected.content_hash
        ):
            raise SourceRevisionMismatchError
        return artifact

    async def _acquire(
        self,
        *,
        request: CaptureRequest,
        source: Source,
        reader: SourceReader,
        expected: SourceRevision | None = None,
    ) -> AcquiredRevision:
        limits = self._runtime.limits
        descriptor = request.file()
        location = descriptor.resolved_location()
        parser = self._runtime.parsers.get(descriptor.format)
        async with reader.open(
            location=location,
            limits=limits,
            expected=expected,
            expected_entry=request.expected_entry,
        ) as acquired:
            content = _raw_bytes(acquired=acquired, max_bytes=limits.max_source_bytes)
            if (
                acquired.origin.reader != location.reader
                or acquired.origin.location != location.path
                or acquired.origin.provider_scope != reader.provider_scope
                or (
                    request.expected_entry is not None
                    and request.expected_entry.provider_version is not None
                    and acquired.origin.provider_version != request.expected_entry.provider_version
                )
                or (
                    descriptor.expected_hash is not None
                    and descriptor.expected_hash != acquired.content_hash
                )
                or (
                    expected is not None
                    and expected.revision_id.value != acquired.content_hash.value
                )
            ):
                raise SourceRevisionMismatchError
            _verify_format(source=descriptor, content=content, limits=limits)
            if parser is None and (
                (isinstance(descriptor, PDF) and descriptor.pages is not None)
                or (isinstance(descriptor, Excel) and descriptor.sheets is not None)
            ):
                raise MissingCapabilityError(
                    message="Configure a parser for the selected pages or sheets",
                )
            revision = SourceRevision(
                project_id=source.project_id,
                source_id=source.id,
                revision_id=SourceRevisionId(value=acquired.content_hash.value),
                byte_length=acquired.byte_length,
                origin=acquired.origin,
            )
            implementation = (
                ("original-only", "1")
                if parser is None
                else (parser.parser_id, parser.parser_version)
            )
            fingerprint = _format_fingerprint(descriptor=descriptor, implementation=implementation)
            profile, evidence, document, excerpts = None, (), None, ()
            if parser is not None:
                parsed = await run_parser(
                    parse=lambda: parse_file(
                        parser=parser,
                        acquired=acquired,
                        descriptor=descriptor,
                        limits=limits,
                    ),
                )
                fingerprint = parsed.capture_fingerprint(configuration_fingerprint=fingerprint)
                processing = ProcessingRecord(
                    source=revision,
                    fingerprint=fingerprint,
                    parser_id=implementation[0],
                    parser_version=implementation[1],
                )
                profile, evidence = await run_parser(
                    parse=lambda: parsed.capture(processing=processing, descriptor=descriptor),
                )
                if self._runtime.retain_parsed:
                    document = parsed.retained_document(processing=processing)
                if self._runtime.retain_excerpts:
                    excerpts = capture_excerpts(
                        evidence=evidence, parts=(*parsed.texts, *parsed.tables)
                    )
        return AcquiredRevision(
            ingestion=IngestedSource(
                revision=revision,
                processing_fingerprint=fingerprint,
                evidence=evidence,
            ),
            profile=profile,
            content=content,
            document=document,
            excerpts=excerpts,
        )

    async def _commit(  # noqa: PLR0913 - Bind the exact capture and its transactional effects.
        self,
        *,
        captured: IngestedSource,
        profile: SourceProfile | None,
        artifact: Artifact | None,
        source: Source,
        claims: Sequence[tuple[Invocation, Lease]],
        transaction: SourceTransaction,
        intent: OriginalWriteIntent | None,
        payload: ParsedPayload | StatementPayload | None = None,
        document: RetainedDocument | None = None,
        excerpts: tuple[RetainedExcerpt, ...] = (),
    ) -> IngestedSource:
        async with transaction.begin():
            renewed = [
                (item, await transaction.operations.renew(invocation=item, lease=lease))
                for item, lease in claims
            ]
            invocation = renewed[0][0]
            prior = None
            revision = captured.revision
            if invocation.operation == "ingest_source_revision":
                prior = await transaction.sources.get(
                    project_id=self._project_id, source_id=source.id
                )
                existing = await transaction.sources.revision(
                    project_id=self._project_id,
                    source_id=source.id,
                    revision_id=captured.revision_id,
                )
                if existing is None:
                    source = prior.register_revision(revision=revision)
                    await transaction.sources.save(source=source, expected_version=prior.version)
                    await transaction.sources.add_revision(revision=revision)
                else:
                    source, revision = prior, existing
            else:
                await transaction.sources.save(source=source, expected_version=None)
                await transaction.sources.add_revision(revision=revision)
            copy = (
                None
                if artifact is None
                else OriginalCopy(
                    source=revision,
                    artifact=artifact,
                    verified_hash=artifact.content_hash,
                    copied_at=datetime.now(tz=UTC),
                )
            )
            result = IngestedSource(
                revision=revision,
                processing_fingerprint=captured.processing_fingerprint,
                retained_original=copy,
                evidence=tuple(
                    replace(
                        item, source=revision, processing=replace(item.processing, source=revision)
                    )
                    for item in captured.evidence
                ),
            )
            if profile is not None and profile.source != revision:
                profile = replace(
                    profile,
                    source=revision,
                    processing=replace(profile.processing, source=revision),
                )
            if result.evidence:
                await self._record_evidence(
                    transaction=transaction,
                    result=result,
                    payload=payload,
                )
            if document is not None:
                if not isinstance(transaction.sources, DocumentRepository):
                    raise MissingCapabilityError(message="Configure retained document persistence")
                await transaction.sources.retain_document(
                    document=replace(document, source=revision),
                )
            if excerpts:
                await self._retain_excerpts(
                    repository=transaction.sources,
                    evidence=result.evidence,
                    excerpts=excerpts,
                )
            key = uuid4().hex
            await transaction.sources.add_result(
                project_id=self._project_id,
                key=key,
                result=result,
                profile=profile,
            )
            await transaction.audit.append(
                record=_audit_capture(
                    invocation=invocation, source=source, previous=prior, result=result
                ),
            )
            if intent is not None and artifact is not None:
                await transaction.audit.append(
                    record=AuditRecord(
                        id=AuditId(value=uuid4().hex),
                        project_id=self._project_id,
                        model_id=None,
                        action=AuditAction.COPY_SOURCE_ORIGINAL,
                        outcome=AuditOutcome.SUCCEEDED,
                        actor=invocation.actor,
                        recorded_at=datetime.now(tz=UTC),
                        before=(),
                        after=(artifact,),
                        parent_id=intent.audit_id,
                    )
                )
            outcome = OperationOutcome(resource_kind="source_ingestion", resource_id=key)
            for item, lease in renewed:
                await transaction.operations.complete(invocation=item, lease=lease, outcome=outcome)
            return result

    @staticmethod
    async def _retain_excerpts(
        *,
        repository: SourceRepository,
        evidence: Sequence[Evidence],
        excerpts: Sequence[RetainedExcerpt],
    ) -> None:
        if not isinstance(repository, ExcerptRepository):
            raise MissingCapabilityError(message="Configure evidence excerpt persistence")
        citations = {item.id: item for item in evidence}
        for excerpt in excerpts:
            await repository.retain_excerpt(
                excerpt=replace(excerpt, evidence=citations[excerpt.evidence.id]),
            )

    @staticmethod
    async def _record_evidence(
        *,
        transaction: SourceTransaction,
        result: IngestedSource,
        payload: ParsedPayload | StatementPayload | None,
    ) -> None:
        if not isinstance(transaction.sources, ParsedSourceRepository):
            raise MissingCapabilityError(message="Configure source citation persistence")
        for evidence in result.evidence:
            await transaction.sources.add_evidence(evidence=evidence)
        if payload is None:
            return
        origin = result.revision.origin
        if isinstance(payload, StatementPayload):
            if not isinstance(origin, StatementOrigin):
                raise SourceRevisionMismatchError
            if not isinstance(transaction.sources, StatementRepository):
                raise MissingCapabilityError(message="Configure statement capture persistence")
            await transaction.sources.retain_statement(
                revision=result.revision,
                payload=replace(payload, origin=origin),
            )
        else:
            if not isinstance(origin, ParsedSourceOrigin):
                raise SourceRevisionMismatchError
            await transaction.sources.retain_payload(
                revision=result.revision,
                payload=replace(payload, origin=origin),
            )

    async def get(self, *, name: str | None, source_id: SourceId | None) -> Source:
        """Resolve exactly one scoped source selector."""
        if (name is None) == (source_id is None):
            raise ValueError("Supply exactly one source name or ID")
        async with (
            source_transaction(resources=self._resources) as transaction,
            transaction.begin(),
        ):
            if source_id is not None:
                require_exact(value=source_id, expected=SourceId, field="Source ID")
                return await transaction.sources.get(
                    project_id=self._project_id, source_id=source_id
                )
            if name is None:
                raise ValueError("Supply a source name or ID")
            require_lookup_name(name=name)
            source = await transaction.sources.find_by_name(project_id=self._project_id, name=name)
            if source is None:
                raise SourceNotFoundError
            return source

    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[Source]:
        """Read a page of detached source identities."""
        async with (
            source_transaction(resources=self._resources) as transaction,
            transaction.begin(),
        ):
            return await transaction.sources.list(
                project_id=self._project_id, limit=limit, cursor=cursor
            )

    @asynccontextmanager
    async def _open_original(
        self, *, revision: SourceRevision, digest: ContentHash
    ) -> AsyncGenerator[AcquiredSource]:
        origin = revision.origin
        if not isinstance(origin, FileOrigin):
            raise TypeError("Select a file-based source revision to copy original bytes")
        reader = self._runtime.reader(name=origin.reader)
        if origin.provider_scope != reader.provider_scope:
            raise SourceRevisionMismatchError
        location = ReaderLocation(reader=origin.reader, path=origin.location)
        limits = self._runtime.limits
        try:
            async with (
                self._runtime.gate,
                reader.open(
                    location=location,
                    limits=limits,
                    expected=revision,
                ) as acquired,
            ):
                if (
                    acquired.origin.reader != origin.reader
                    or acquired.origin.provider_scope != origin.provider_scope
                    or acquired.origin.location != origin.location
                    or acquired.origin.provider_version != origin.provider_version
                    or acquired.byte_length != revision.byte_length
                    or acquired.content_hash != digest
                ):
                    raise SourceRevisionMismatchError
                yield acquired
        except OSError:
            raise SourceReadError(
                message="Open the exact original using its configured reader."
            ) from None

    async def _original_bytes(self, *, revision: SourceRevision, digest: ContentHash) -> bytes:
        async with self._open_original(revision=revision, digest=digest) as acquired:
            return _raw_bytes(acquired=acquired, max_bytes=self._runtime.limits.max_source_bytes)

    async def copy_original(
        self,
        *,
        actor: str,
        revision: SourceRevision,
        destination: CopyTo,
        idempotency_key: str | None,
    ) -> OriginalCopy:
        """Verify the registered original and journal a separate immutable copy."""
        require_exact(value=revision, expected=SourceRevision, field="Source revision")
        require_exact(value=destination, expected=CopyTo, field="Original copy destination")
        require_text(value=actor, field="Actor")
        if revision.project_id != self._project_id:
            raise ScopeMismatchError
        if not isinstance(revision.origin, FileOrigin):
            raise TypeError("Select a file-based source revision to copy original bytes")
        async with source_transaction(resources=self._resources) as transaction:
            async with transaction.begin():
                registered = await transaction.sources.revision(
                    project_id=self._project_id,
                    source_id=revision.source_id,
                    revision_id=revision.revision_id,
                )
                if registered != revision:
                    raise SourceRevisionMismatchError
            return await self._copy_original(
                transaction=transaction,
                revision=revision,
                destination=destination,
                actor=actor,
                idempotency_key=idempotency_key,
            )

    async def _copy_original(
        self,
        *,
        transaction: SourceTransaction,
        revision: SourceRevision,
        destination: CopyTo,
        actor: str,
        idempotency_key: str | None,
    ) -> OriginalCopy:
        store = self._runtime.stores.get(destination.store)
        if store is None:
            raise MissingCapabilityError(message="Configure the selected original store")
        digest = ContentHash(value=revision.revision_id.value)
        key = _original_key(project_id=self._project_id, digest=digest)
        expected = Artifact(
            project_id=self._project_id, store=destination.store, key=key, content_hash=digest
        )

        async def lookup() -> Artifact | None:
            return await store.verify(
                project_id=self._project_id,
                key=key,
                digest=digest,
                byte_length=revision.byte_length,
            )

        async def verified(artifact: Artifact) -> bool:
            return await lookup() == artifact

        async def write(*, retry: bool) -> Artifact:
            if retry and (existing := await lookup()) is not None:
                return existing
            content = await self._original_bytes(revision=revision, digest=digest)
            return await store.put(
                project_id=self._project_id,
                key=key,
                digest=digest,
                content=content,
            )

        result = await deliver(
            transaction=transaction,
            request=DeliveryRequest(
                action=AuditAction.COPY_SOURCE_ORIGINAL,
                actor=actor,
                idempotency_key=idempotency_key,
                intent=(
                    store.provider_scope,
                    record_value(value=revision),
                    record_value(value=expected),
                ),
                requested=expected,
                resource=AuditResource(
                    resource_id=revision.revision_id,
                    revision=None,
                    content_hash=digest,
                ),
            ),
            write=write,
            verify=verified,
        )
        return OriginalCopy(
            source=revision,
            artifact=result.artifact,
            verified_hash=digest,
            copied_at=result.recorded_at,
        )

    async def get_revision(
        self, *, source_id: SourceId, revision_id: SourceRevisionId
    ) -> SourceRevision:
        """Read an exact revision without touching its original bytes."""
        require_exact(value=source_id, expected=SourceId, field="Source ID")
        require_exact(value=revision_id, expected=SourceRevisionId, field="Revision ID")
        async with (
            source_transaction(resources=self._resources) as transaction,
            transaction.begin(),
        ):
            _ = await transaction.sources.get(project_id=self._project_id, source_id=source_id)
            result = await transaction.sources.revision(
                project_id=self._project_id,
                source_id=source_id,
                revision_id=revision_id,
            )
            if result is None:
                raise SourceNotFoundError
            return result

    async def list_revisions(
        self,
        *,
        source_id: SourceId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[SourceRevision]:
        """Read exact revisions ordered by acceptance."""
        require_exact(value=source_id, expected=SourceId, field="Source ID")
        async with (
            source_transaction(resources=self._resources) as transaction,
            transaction.begin(),
        ):
            _ = await transaction.sources.get(project_id=self._project_id, source_id=source_id)
            return await transaction.sources.list_revisions(
                project_id=self._project_id,
                source_id=source_id,
                limit=limit,
                cursor=cursor,
            )

    async def profile(
        self, *, actor: str, revision: SourceRevision, processing_fingerprint: str | None
    ) -> SourceProfile:
        """Return the recorded profile of this exact revision and audit the inspection."""
        require_text(value=actor, field="Actor")
        require_exact(value=revision, expected=SourceRevision, field="Source revision")
        if processing_fingerprint is not None:
            require_text(value=processing_fingerprint, field="Processing fingerprint")
        if revision.project_id != self._project_id:
            raise ScopeMismatchError
        async with (
            source_transaction(resources=self._resources) as transaction,
            transaction.begin(),
        ):
            current = await transaction.sources.revision(
                project_id=self._project_id,
                source_id=revision.source_id,
                revision_id=revision.revision_id,
            )
            if current != revision:
                raise SourceRevisionMismatchError
            profile = await transaction.sources.profile(
                revision=revision, processing_fingerprint=processing_fingerprint
            )
            if profile is None:
                raise MissingCapabilityError(
                    message="Capture this exact revision with a configured format parser",
                )
            await transaction.audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=self._project_id,
                    model_id=None,
                    action=AuditAction.PROFILE_SOURCE,
                    outcome=AuditOutcome.SUCCEEDED,
                    actor=actor,
                    recorded_at=datetime.now(tz=UTC),
                    before=(),
                    after=(
                        AuditResource(
                            resource_id=revision.revision_id,
                            revision=None,
                            content_hash=hash_json(value=record_value(value=profile)),
                        ),
                    ),
                )
            )
            return profile
