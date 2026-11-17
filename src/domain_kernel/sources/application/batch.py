"""Capture complete folder selections before running bounded independent ingestions."""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Literal, final
from uuid import uuid4

from domain_kernel._shared.application.persistence import Invocation, OperationOutcome
from domain_kernel._shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel._shared.domain.naming import resolve_names
from domain_kernel.projects.domain.identifiers.project_id import ProjectId  # noqa: TC001 - Manifest schema.
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import (
    DomainKernelError,
    IdempotencyConflictError,
    MissingCapabilityError,
    OperationInProgressError,
    ResourceLimitError,
    SourceNotFoundError,
    SourceReadError,
    StaleStateError,
)
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validation import is_non_string_sequence, require_exact, require_text
from domain_kernel.sources.application.contracts import (
    CSV,
    PDF,
    BatchIngestionResult,
    Excel,
    IngestionFailure,
    IngestionStage,
    IngestionSuccess,
    Ontology,
    ReaderLocation,
    SourceEntry,
    SourceEntryKind,
    SourceFolder,
    SourceInput,
    Word,
)
from domain_kernel.sources.application.manifests import (
    ManifestItem,
    ManifestPayload,
    SourceManifest,
    child_request_key,
)
from domain_kernel.sources.application.service import CaptureRequest, source_transaction
from domain_kernel.sources.domain.errors.source_already_exists_error import SourceAlreadyExistsError
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
from domain_kernel.sources.domain.paths import matches_globs

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.application.persistence import Transaction, UnitOfWorkFactory
    from domain_kernel.sources.application.contracts import FileDescriptor
    from domain_kernel.sources.application.ports import SourceReader
    from domain_kernel.sources.application.service import SourceRuntime, Sources

_FILE_ERRORS = (
    SourceNotFoundError,
    SourceReadError,
    SourceAlreadyExistsError,
    SourceRevisionMismatchError,
    StaleStateError,
    ResourceLimitError,
    MissingCapabilityError,
    OperationInProgressError,
    IdempotencyConflictError,
)

_LIST_ERRORS = (
    SourceNotFoundError,
    SourceReadError,
    ResourceLimitError,
    MissingCapabilityError,
    StaleStateError,
    OperationInProgressError,
)


@dataclass(slots=True)
class _ListingBudget:
    maximum: int
    used: int = 0

    def account(self, *, size: int) -> None:
        self.used += size
        if self.used > self.maximum:
            raise ResourceLimitError(message="Choose a folder selection with fewer entries")


_FILE_FORMATS: dict[str, type[PDF | CSV | Word | Excel]] = {
    ".pdf": PDF,
    ".csv": CSV,
    ".xlsx": Excel,
    ".docx": Word,
}
_ONTOLOGY_FORMATS: dict[str, Literal["rdfxml", "turtle", "ntriples", "jsonld"]] = {
    ".rdf": "rdfxml",
    ".owl": "rdfxml",
    ".ttl": "turtle",
    ".nt": "ntriples",
    ".jsonld": "jsonld",
}


def _descriptor(*, location: ReaderLocation) -> FileDescriptor:
    suffix = PurePosixPath(location.path).suffix.lower()
    file_type = _FILE_FORMATS.get(suffix)
    if file_type is not None:
        return file_type(location=location)
    ontology_format = _ONTOLOGY_FORMATS.get(suffix)
    if ontology_format is not None:
        return Ontology(location=location, format=ontology_format)
    raise MissingCapabilityError(message="Select a supported file format")


def _folder_item(
    *,
    entry: SourceEntry,
    folder: SourceFolder,
    manifest_id: SourceManifestId,
) -> ManifestItem:
    if entry.kind is SourceEntryKind.LINK:
        return ManifestItem(
            file=entry,
            stage=IngestionStage.LISTING,
            issue=Issue(code="source_link", path=(), message="Select an original without links."),
        )
    try:
        descriptor = _descriptor(location=entry.location)
    except MissingCapabilityError as error:
        return ManifestItem(
            file=entry,
            stage=IngestionStage.NAMING,
            issue=Issue(code=error.code, path=(), message=str(error)),
        )
    stem = PurePosixPath(entry.location.path).stem
    try:
        name, label = resolve_names(name=None, display_name=stem)
        resolved = name if folder.name_prefix is None else f"{folder.name_prefix}-{name}"
        return ManifestItem(
            file=entry,
            input=SourceInput(
                source=descriptor,
                name=resolved,
                display_name=label,
                retain_original=folder.retain_original,
                idempotency_key=child_request_key(manifest_id=manifest_id, entry=entry),
            ),
        )
    except ValueError:
        return ManifestItem(
            file=entry,
            stage=IngestionStage.NAMING,
            issue=Issue(
                code="source_name",
                path=(),
                message="Choose an explicit source name for this file.",
            ),
        )


async def _children(
    *,
    reader: SourceReader,
    folder: ReaderLocation,
    runtime: SourceRuntime,
    budget: _ListingBudget,
) -> tuple[SourceEntry, ...]:
    found: dict[str, SourceEntry] = {}
    cursors: set[str] = set()
    cursor = None
    while True:
        page = await reader.list_children(location=folder, limits=runtime.selection, cursor=cursor)
        budget.account(size=len(page.items))
        for item in page.items:
            if (
                item.provider_scope != reader.provider_scope
                or item.location.reader != folder.reader
                or PurePosixPath(item.location.path).parent != PurePosixPath(folder.path)
                or item.location.path in found
            ):
                raise SourceReadError(
                    message="List distinct immediate children in the bound reader."
                )
            found[item.location.path] = item
        cursor = page.next_cursor
        if cursor is None:
            return tuple(found.values())
        if cursor.value in cursors:
            raise SourceReadError(message="Use a reader with a forward-moving listing cursor.")
        cursors.add(cursor.value)


async def _expand(
    *,
    selection: SourceFolder,
    reader: SourceReader,
    runtime: SourceRuntime,
    budget: _ListingBudget,
) -> tuple[SourceEntry, ...]:
    origin = PurePosixPath(selection.location.path)
    pending = deque([(selection.location, 0)])
    result: list[SourceEntry] = []
    async with runtime.gate, asyncio.timeout(runtime.selection.listing_timeout_seconds):
        while pending:
            location, depth = pending.popleft()
            for item in await _children(
                reader=reader, folder=location, runtime=runtime, budget=budget
            ):
                if item.kind is SourceEntryKind.FOLDER:
                    if selection.recursive:
                        if depth >= runtime.selection.max_listing_depth:
                            raise ResourceLimitError(message="Select a shallower folder tree.")
                        pending.append((item.location, depth + 1))
                    continue
                relative = PurePosixPath(item.location.path).relative_to(origin).as_posix()
                if matches_globs(
                    path=relative,
                    include=tuple(selection.include),
                    exclude=tuple(selection.exclude),
                ):
                    result.append(item)
    return tuple(sorted(result, key=lambda entry: entry.location.path))


@dataclass(frozen=True, kw_only=True)
class _Selected:
    input: SourceInput
    entry: SourceEntry | None = None

    def capture(self) -> CaptureRequest:
        return CaptureRequest(
            source=self.input.source,
            name=self.input.name,
            display_name=self.input.display_name,
            retain_original=self.input.retain_original,
            idempotency_key=self.input.idempotency_key,
            expected_entry=self.entry,
        )


@dataclass(slots=True)
class _Job:
    selected: _Selected
    aliases: list[_Selected] = field(default_factory=list)
    result: IngestionSuccess | IngestionFailure | None = None


def _failure(
    *,
    selection: SourceInput | SourceFolder,
    stage: IngestionStage,
    error: DomainKernelError,
    location: ReaderLocation | None,
) -> IngestionFailure:
    return IngestionFailure(
        input=selection,
        stage=stage,
        location=location,
        issue=Issue(code=error.code, path=(), message=str(error)),
        retryable=error.retryable,
    )


def _scope_budget(*, override: int | None, configured: int, field: str) -> int:
    if override is None:
        return configured
    require_exact(value=override, expected=int, field=field)
    if not 1 <= override <= configured:
        raise ValueError("Use a positive override within the configured source limit")
    return override


@final
class SourceBatch:
    """Materialize frozen manifest selections and process them with fixed worker counts."""

    def __init__(
        self,
        *,
        project_id: ProjectId,
        resources: UnitOfWorkFactory[Transaction],
        runtime: SourceRuntime,
        sources: Sources,
    ) -> None:
        """Share the client's reader gates and the project ingestion service."""
        self._project_id = project_id
        self._resources = resources
        self._runtime = runtime
        self._sources = sources

    async def _manifest(
        self,
        *,
        actor: str,
        folder: SourceFolder,
        budget: _ListingBudget,
    ) -> SourceManifest:
        reader = self._runtime.reader(name=folder.location.reader)
        request = Invocation.resolve(
            project_id=self._project_id,
            model_id=None,
            actor=actor,
            operation="capture_source_manifest",
            key=folder.idempotency_key,
            intent=(reader.provider_scope, folder.model_dump_json(exclude={"idempotency_key"})),
        )
        async with source_transaction(resources=self._resources) as transaction:
            async with transaction.begin():
                claim = await transaction.operations.claim(invocation=request, owner=uuid4().hex)
                if isinstance(claim, OperationOutcome):
                    data = await transaction.sources.manifest(
                        project_id=self._project_id,
                        identifier=SourceManifestId(value=claim.resource_id),
                    )
                    manifest = SourceManifest.model_validate_json(data)
                    if (
                        manifest.request_hash != request.request_hash
                        or manifest.id.value != claim.resource_id
                    ):
                        raise StaleStateError(
                            message="Reload the original complete folder manifest"
                        )
                    return manifest
            try:
                entries = await _expand(
                    selection=folder, reader=reader, runtime=self._runtime, budget=budget
                )
                identity = SourceManifestId(value=uuid4().hex)
                content = ManifestPayload(
                    id=identity,
                    project_id=self._project_id,
                    provider_scope=reader.provider_scope,
                    selection=folder,
                    actor=actor,
                    request_hash=request.request_hash,
                    created_at=datetime.now(tz=UTC),
                    items=tuple(
                        _folder_item(entry=item, folder=folder, manifest_id=identity)
                        for item in entries
                    ),
                )
                manifest = SourceManifest(
                    id=identity,
                    project_id=content.project_id,
                    provider_scope=content.provider_scope,
                    selection=content.selection,
                    actor=content.actor,
                    request_hash=content.request_hash,
                    created_at=content.created_at,
                    items=content.items,
                    content_hash=content.fingerprint(),
                )
                async with transaction.begin():
                    renewed = await transaction.operations.renew(invocation=request, lease=claim)
                    await transaction.sources.add_manifest(
                        project_id=self._project_id,
                        identifier=identity,
                        content=manifest.model_dump_json().encode(),
                        entry_keys=tuple(
                            item.input.idempotency_key
                            for item in manifest.items
                            if item.input is not None and item.input.idempotency_key is not None
                        ),
                    )
                    await transaction.audit.append(
                        record=AuditRecord(
                            id=AuditId(value=uuid4().hex),
                            project_id=self._project_id,
                            model_id=None,
                            action=AuditAction.CAPTURE_SOURCE_MANIFEST,
                            outcome=AuditOutcome.SUCCEEDED,
                            actor=actor,
                            recorded_at=content.created_at,
                            before=(),
                            after=(
                                AuditResource(
                                    resource_id=identity,
                                    revision=None,
                                    content_hash=manifest.content_hash,
                                ),
                            ),
                        ),
                    )
                    await transaction.operations.complete(
                        invocation=request,
                        lease=renewed,
                        outcome=OperationOutcome(
                            resource_kind="source_manifest", resource_id=identity.value
                        ),
                    )
            except BaseException:
                with suppress(StaleStateError):
                    async with transaction.begin():
                        await transaction.operations.release(invocation=request, lease=claim)
                raise
            else:
                return manifest

    async def _selection(
        self,
        *,
        actor: str,
        sources: Sequence[SourceInput | SourceFolder],
    ) -> tuple[_Selected | IngestionFailure, ...]:
        budget = _ListingBudget(maximum=self._runtime.selection.max_listing_entries)
        result: list[_Selected | IngestionFailure] = []
        for item in sources:
            if isinstance(item, SourceInput):
                result.append(_Selected(input=item))
                continue
            try:
                manifest = await self._manifest(actor=actor, folder=item, budget=budget)
            except _LIST_ERRORS as error:
                result.append(
                    _failure(
                        selection=item,
                        stage=IngestionStage.LISTING,
                        error=error,
                        location=item.location,
                    )
                )
                continue
            except TimeoutError:
                result.append(
                    IngestionFailure(
                        input=item,
                        stage=IngestionStage.LISTING,
                        location=item.location,
                        retryable=True,
                        issue=Issue(
                            code="source_listing_timeout",
                            path=(),
                            message="Retry a smaller folder selection.",
                        ),
                    )
                )
                continue
            for entry in manifest.items:
                if entry.input is not None:
                    result.append(_Selected(input=entry.input, entry=entry.file))
                elif entry.issue is not None and entry.stage is not None:
                    result.append(
                        IngestionFailure(
                            input=item,
                            stage=entry.stage,
                            issue=entry.issue,
                            retryable=False,
                            location=entry.file.location,
                        )
                    )
        return tuple(result)

    async def ingest(
        self,
        *,
        actor: str,
        inputs: Sequence[SourceInput | SourceFolder],
        max_concurrent_sources: int | None,
        max_files: int | None,
    ) -> BatchIngestionResult:
        """Process exact selected paths with stable order and per-input failure outcomes."""
        require_text(value=actor, field="Actor")
        if not is_non_string_sequence(inputs) or any(
            type(item) not in (SourceFolder, SourceInput) for item in inputs
        ):
            raise TypeError("Supply a sequence of typed file and folder selections")
        parallel = _scope_budget(
            override=max_concurrent_sources,
            configured=self._runtime.limits.max_concurrent_sources,
            field="Concurrent sources",
        )
        limit = _scope_budget(
            override=max_files,
            configured=self._runtime.selection.max_files,
            field="Files",
        )
        selected = await self._selection(actor=actor, sources=tuple(inputs))
        ordered, jobs = _plan(selected=selected, limit=limit)
        queue = deque(jobs)

        async def worker() -> None:
            while queue:
                job = queue.popleft()
                items = (job.selected, *job.aliases)
                acquired = next((item for item in items if item.entry is not None), job.selected)
                source_input = job.selected.input
                try:
                    result = await self._sources.ingest(
                        actor=actor,
                        request=acquired.capture(),
                        aliases=tuple(item.capture() for item in items if item is not acquired),
                    )
                except _FILE_ERRORS as error:
                    job.result = _failure(
                        selection=source_input,
                        stage=IngestionStage.INGESTION,
                        error=error,
                        location=source_input.source.resolved_location(),
                    )
                else:
                    job.result = IngestionSuccess(input=source_input, ingested_source=result)

        async with asyncio.TaskGroup() as tasks:
            for _ in range(min(parallel, len(jobs))):
                _ = tasks.create_task(worker())
        return BatchIngestionResult(
            items=tuple(
                outcome
                for item in ordered
                if (outcome := (item.result if isinstance(item, _Job) else item)) is not None
            ),
        )


def _plan(
    *,
    selected: Sequence[_Selected | IngestionFailure],
    limit: int,
) -> tuple[tuple[_Job | IngestionFailure, ...], tuple[_Job, ...]]:
    ordered: list[_Job | IngestionFailure] = []
    paths: dict[tuple[str, str], _Job] = {}
    names: dict[str, tuple[str, str]] = {}
    for item in selected:
        if isinstance(item, IngestionFailure):
            ordered.append(item)
            continue
        descriptor = item.input.source
        location = descriptor.resolved_location()
        path = (location.reader, location.path)
        name, label = resolve_names(name=item.input.name, display_name=item.input.display_name)
        previous = paths.get(path)
        if previous is not None:
            other = previous.selected.input
            effective = (
                name,
                label,
                descriptor.model_dump_json(exclude={"path", "location"}),
                item.input.retain_original,
            )
            other_name, other_label = resolve_names(
                name=other.name, display_name=other.display_name
            )
            compared = (
                other_name,
                other_label,
                other.source.model_dump_json(exclude={"path", "location"}),
                other.retain_original,
            )
            if effective != compared:
                raise ValueError("Overlapping source paths must use equivalent names and options")
            if item.entry is not None and any(
                other.entry is not None and other.entry != item.entry
                for other in (previous.selected, *previous.aliases)
            ):
                raise SourceRevisionMismatchError
            previous.aliases.append(item)
            continue
        if name in names:
            raise SourceAlreadyExistsError
        if len(paths) == limit:
            raise ResourceLimitError(message="Select fewer distinct files in this batch")
        names[name] = path
        job = _Job(selected=item)
        paths[path] = job
        ordered.append(job)
    return tuple(ordered), tuple(paths.values())
