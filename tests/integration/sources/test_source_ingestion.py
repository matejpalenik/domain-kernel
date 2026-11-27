"""Check immutable acquired revisions, replay and frozen file selections."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from threading import Event
from typing import TYPE_CHECKING, override

import pytest

from domain_kernel import (
    PDF,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    ContentHash,
    CopyTo,
    FileOrigin,
    IdempotencyConflictError,
    ParsedChunk,
    ReaderLocation,
    ResourceLimitError,
    ScopeMismatchError,
    SourceAlreadyExistsError,
    SourceFolder,
    SourceInput,
    SourceReader,
    SourceReadError,
    SourceRevisionMismatchError,
)
from domain_kernel.configuration import FilesystemReader, InMemoryProcessing, SourceSelectionLimits
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.infrastructure.persistence.repositories import (
    sqlalchemy_idempotency_repository,
)
from domain_kernel.sources.infrastructure.filesystem_reader import FilesystemSourceReader
from domain_kernel.sources.infrastructure.sqlite_sources import SQLiteSources

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterator
    from pathlib import Path

    from domain_kernel import (
        AcquiredSource,
        FileDescriptor,
        Page,
        PageCursor,
        ProcessingLimits,
        ProjectId,
        SourceEntry,
        SourceRevision,
    )
    from domain_kernel.shared.application.idempotency.invocation import Invocation
    from domain_kernel.shared.application.idempotency.lease import Lease
    from tests.support.persistence.database_backend import DatabaseBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_FIRST_PDF = b"%PDF-1.7\n% source acquisition fixture one\n%%EOF"
_SECOND_PDF = b"%PDF-1.7\n% source acquisition fixture two\n%%EOF"


def _file_location(*, revision: SourceRevision) -> str:
    assert isinstance(revision.origin, FileOrigin)
    return revision.origin.location


async def test_ingest_pins_raw_bytes_and_replays_before_acquisition(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    original = inputs / "original.pdf"
    _ = original.write_bytes(_FIRST_PDF)
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
    )
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    first = await project.ingest_source(
        actor="author",
        source=PDF(path="original.pdf", expected_hash=Hashing.hash_bytes(content=_FIRST_PDF)),
        name="legislation",
        idempotency_key="acquire-first",
    )
    assert first.revision_id.value == Hashing.hash_bytes(content=_FIRST_PDF).value
    assert first.revision.byte_length == len(_FIRST_PDF)
    assert first.retained_original is None
    assert not first.evidence
    _ = original.write_bytes(_SECOND_PDF)
    second = await project.ingest_source_revision(
        actor="reviewer",
        source_id=first.source_id,
        source=PDF(path="original.pdf"),
    )
    assert first.revision_id != second.revision_id
    assert second.source_id == first.source_id
    original.unlink()
    reopened = await Client(config=config).get_project(name="recruitment")
    assert await reopened.get_source(name="legislation") == await reopened.get_source(
        source_id=first.source_id,
    )
    assert (
        await reopened.get_source_revision(
            source_id=first.source_id,
            revision_id=first.revision_id,
        )
        == first.revision
    )
    assert (
        await reopened.ingest_source(
            actor="author",
            source=PDF(
                path="original.pdf", expected_hash=ContentHash(value=first.revision_id.value)
            ),
            name="legislation",
            idempotency_key="acquire-first",
        )
        == first
    )


async def test_folder_replay_uses_frozen_paths_and_keeps_other_successes(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    nested = inputs / "working" / "nested"
    nested.mkdir(parents=True)
    _ = (nested / "document.pdf").write_bytes(_FIRST_PDF)
    _ = (inputs / "direct.pdf").write_bytes(_SECOND_PDF)
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
    )
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    selected = SourceFolder(
        location=ReaderLocation(reader="inputs", path="working"),
        recursive=True,
        include=["**/*.pdf"],
        name_prefix="frozen",
        idempotency_key="selected",
    )
    initial = await project.ingest_sources(
        actor="author",
        sources=[
            selected,
            SourceInput(source=PDF(path="missing.pdf"), name="missing"),
            SourceInput(source=PDF(path="direct.pdf"), name="direct"),
        ],
    )
    assert {_file_location(revision=revision) for revision in initial.revisions} == {
        "working/nested/document.pdf",
        "direct.pdf",
    }
    (missing,) = initial.failures
    assert missing.code == missing.issue.code
    assert missing.message == missing.issue.message
    assert missing.severity is missing.issue.severity
    _ = (nested / "new.pdf").write_bytes(_SECOND_PDF)
    (nested / "document.pdf").unlink()
    reopened = await Client(config=config).get_project(name="recruitment")
    replayed = await reopened.ingest_sources(actor="author", sources=[selected])
    assert replayed.revisions == initial.revisions[:1]


async def test_overlapping_folders_replay_each_manifest_key_with_one_ingestion(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    subfolder = inputs / "legislation"
    subfolder.mkdir(parents=True)
    pdf = subfolder / "act.pdf"
    _ = pdf.write_bytes(_FIRST_PDF)
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
    )
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    top = SourceFolder(
        location=ReaderLocation(reader="inputs", path="."),
        recursive=True,
        idempotency_key="top-selection",
    )
    nested = SourceFolder(
        location=ReaderLocation(reader="inputs", path="legislation"),
        idempotency_key="nested-selection",
    )
    captured = await project.ingest_sources(actor="author", sources=[top, nested])
    (revision,) = captured.revisions
    pdf.unlink()
    replay = await project.ingest_sources(actor="author", sources=[nested])
    assert replay.revisions == (revision,)
    direct_retry = await project.ingest_sources(
        actor="author",
        sources=[captured.successes[0].input],
    )
    assert direct_retry.revisions == (revision,)
    journal = await project.get_audit_history()
    assert sum(item.action.value == "ingest_source" for item in journal.items) == 1


async def test_requested_original_recovers_from_a_lost_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    path = inputs / "original.pdf"
    _ = path.write_bytes(_FIRST_PDF)
    config = ClientConfiguration(
        base_dir=tmp_path,
        readers=[FilesystemReader(name="inputs", root="inputs")],
    )
    project = await Client(config=config).create_project(actor="author", name="recruitment")

    async def interrupt_commit(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Interrupted after the artifact write")

    with monkeypatch.context() as isolated:
        isolated.setattr(SQLiteSources, "add_result", interrupt_commit)
        with pytest.raises(RuntimeError, match="Interrupted"):
            _ = await project.ingest_source(
                actor="author",
                name="original",
                source=PDF(path="original.pdf"),
                retain_original=CopyTo(store="artifacts"),
                idempotency_key="retain-original",
            )
    assert not (await project.list_sources()).items
    path.unlink()
    reopened = await Client(config=config).get_project(name=project.name)
    recovered = await reopened.ingest_source(
        actor="author",
        name="original",
        source=PDF(path="original.pdf"),
        retain_original=CopyTo(store="artifacts"),
        idempotency_key="retain-original",
    )
    assert recovered.retained_original is not None
    artifact = recovered.retained_original.artifact
    assert artifact.content_hash == Hashing.hash_bytes(content=_FIRST_PDF)
    assert (tmp_path / ".domain-kernel" / "artifacts" / artifact.key).read_bytes() == _FIRST_PDF


class _TestParser:
    @property
    def parser_id(self) -> str:
        return "test-parser"

    @property
    def parser_version(self) -> str:
        return "1"

    def parse(
        self,
        *,
        content: AcquiredSource,
        descriptor: FileDescriptor,
        limits: ProcessingLimits,
    ) -> Iterator[ParsedChunk]:
        assert type(descriptor) is PDF
        assert content.stream.read(size=5) == b"%PDF-"
        assert content.byte_length <= limits.max_source_bytes
        yield ParsedChunk(text="Verified processing output.", section="Definitions", page=1)


async def test_processing_uses_bounded_host_parser_and_preserves_exact_profile(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    original = inputs / "original.pdf"
    _ = original.write_bytes(_FIRST_PDF)
    readers = [FilesystemReader(name="inputs", root="inputs")]
    adapters = ClientIntegrations(format_parsers={"pdf": _TestParser()})
    limited = Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            readers=readers,
            processing=InMemoryProcessing(max_expanded_bytes=4),
        ),
        integrations=adapters,
    )
    project = await limited.create_project(actor="author", name="recruitment")
    with pytest.raises(ResourceLimitError):
        _ = await project.ingest_source(
            actor="author",
            name="oversized",
            source=PDF(path="original.pdf", pages=[1]),
        )
    assert not (await project.list_sources()).items
    config = ClientConfiguration(base_dir=tmp_path, readers=readers)
    normal = await Client(config=config, integrations=adapters).get_project(name=project.name)
    acquired = await normal.ingest_source(
        actor="author",
        name="legislation",
        source=PDF(path="original.pdf", pages=[1]),
    )
    assert acquired.revision_id.value == Hashing.hash_bytes(content=_FIRST_PDF).value
    original.unlink()
    reopened = await Client(config=config).get_project(name=project.name)
    profile = await reopened.profile_source(actor="reviewer", revision=acquired.revision)
    assert profile.processing.fingerprint == acquired.processing_fingerprint
    assert profile.processing.parser_id == "test-parser"
    assert profile.sections == ("Definitions",)
    assert profile.page_count == 1


async def test_scoped_names_and_concurrent_duplicate_bytes_retain_first_revision(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "first.pdf").write_bytes(_FIRST_PDF)
    _ = (tmp_path / "second.pdf").write_bytes(_SECOND_PDF)
    client = Client(config=ClientConfiguration(base_dir=tmp_path))
    project = await client.create_project(actor="author", name="recruitment")
    foreign = await client.create_project(actor="author", name="other")
    first = await project.ingest_source(
        actor="author",
        name="legislation",
        source=PDF(path="first.pdf"),
        idempotency_key="first-key",
    )
    with pytest.raises(IdempotencyConflictError):
        _ = await project.ingest_source(
            actor="different-reviewer",
            name="legislation",
            source=PDF(path="first.pdf"),
            idempotency_key="first-key",
        )
    with pytest.raises(SourceAlreadyExistsError):
        _ = await project.ingest_source(
            actor="author",
            name="legislation",
            source=PDF(path="second.pdf"),
        )
    with pytest.raises(ScopeMismatchError):
        _ = await foreign.get_source(source_id=first.source_id)
    earlier, later = await asyncio.gather(
        project.ingest_source_revision(
            actor="reviewer",
            source_id=first.source_id,
            source=PDF(path="second.pdf"),
        ),
        project.ingest_source_revision(
            actor="editor",
            source_id=first.source_id,
            source=PDF(path="second.pdf"),
        ),
    )
    assert earlier.revision == later.revision
    archived = await project.list_source_revisions(source_id=first.source_id, limit=1)
    assert archived.items == (first.revision,)
    assert archived.next_cursor is not None
    subsequent = await project.list_source_revisions(
        source_id=first.source_id,
        limit=1,
        cursor=archived.next_cursor,
    )
    assert subsequent.items == (earlier.revision,)
    persisted = await project.get_source(name="legislation")
    assert persisted.version == len((*archived.items, *subsequent.items))


async def test_filtered_entries_count_and_invalid_files_leave_no_revision(tmp_path: Path) -> None:
    directory = tmp_path / "work"
    directory.mkdir()
    _ = (directory / "primary.pdf").write_bytes(_FIRST_PDF)
    _ = (directory / "ignored.txt").write_bytes(b"ignored")
    _ = (tmp_path / "external.pdf").write_bytes(_SECOND_PDF)
    (directory / "link.pdf").symlink_to(tmp_path / "external.pdf")
    config = ClientConfiguration(
        base_dir=tmp_path,
        source_selection=SourceSelectionLimits(max_listing_entries=2),
    )
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    blocked = await project.ingest_sources(
        actor="author",
        sources=[
            SourceFolder(
                location=ReaderLocation(reader="inputs", path="work"),
                include=["primary.pdf"],
                idempotency_key="bounded-folder",
            ),
        ],
    )
    (issue,) = blocked.failures
    assert issue.code == "resource_limit"
    assert not blocked.revisions
    with pytest.raises(SourceReadError):
        _ = await project.ingest_source(
            actor="author",
            name="linked",
            source=PDF(path="work/link.pdf"),
        )
    with pytest.raises(SourceRevisionMismatchError):
        _ = await project.ingest_source(
            actor="author",
            name="wrong-pin",
            source=PDF(
                path="work/primary.pdf", expected_hash=Hashing.hash_bytes(content=_SECOND_PDF)
            ),
        )
    assert not (await project.list_sources()).items
    (directory / "ignored.txt").unlink()
    retried = await project.ingest_sources(
        actor="author",
        sources=[
            SourceFolder(
                location=ReaderLocation(reader="inputs", path="work"),
                include=["primary.pdf"],
                idempotency_key="bounded-folder",
            ),
        ],
    )
    assert not retried.failures
    assert [_file_location(revision=item) for item in retried.revisions] == ["work/primary.pdf"]


class _MeteredReader:
    def __init__(self, *, root: Path) -> None:
        self.reader: SourceReader = FilesystemSourceReader(root=root)
        self.maximum: int = 0
        self.active: int = 0

    @property
    def provider_scope(self) -> str:
        return self.reader.provider_scope

    @asynccontextmanager
    async def open(
        self,
        *,
        location: ReaderLocation,
        limits: ProcessingLimits,
        expected: SourceRevision | None = None,
        expected_entry: SourceEntry | None = None,
    ) -> AsyncGenerator[AcquiredSource]:
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        try:
            await asyncio.sleep(0.01)
            async with self.reader.open(
                location=location,
                limits=limits,
                expected=expected,
                expected_entry=expected_entry,
            ) as acquired:
                yield acquired
        finally:
            self.active -= 1

    async def list_children(
        self,
        *,
        location: ReaderLocation,
        limits: SourceSelectionLimits,
        limit: int = 100,
        cursor: PageCursor | None = None,
    ) -> Page[SourceEntry]:
        return await self.reader.list_children(
            location=location,
            limits=limits,
            limit=limit,
            cursor=cursor,
        )


async def test_individual_and_batch_acquisition_share_client_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filenames = ("batch-first", "batch-second", "individual")
    for name in filenames:
        _ = (tmp_path / f"{name}.pdf").write_bytes(_FIRST_PDF)
    reader = _MeteredReader(root=tmp_path)
    client = Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            processing=InMemoryProcessing(max_concurrent_sources=1),
        ),
        integrations=ClientIntegrations(source_readers={"inputs": reader}),
    )
    project = await client.create_project(actor="author", name="recruitment")
    selections = [
        SourceInput(source=PDF(path=f"{name}.pdf"), name=name, idempotency_key=f"{name}-key")
        for name in filenames[:2]
    ]
    manifest_lookup = SQLiteSources.manifest_for_item
    reads_finished = asyncio.Event()
    guards_read = 0

    async def concurrent_lookup(
        self: SQLiteSources,
        *,
        project_id: ProjectId,
        key: str,
    ) -> bytes | None:
        nonlocal guards_read
        result = await manifest_lookup(self, project_id=project_id, key=key)
        guards_read += 1
        if guards_read >= len(selections):
            reads_finished.set()
        _ = await reads_finished.wait()
        return result

    monkeypatch.setattr(SQLiteSources, "manifest_for_item", concurrent_lookup)
    async with asyncio.timeout(5):
        result, single = await asyncio.gather(
            project.ingest_sources(actor="author", sources=selections),
            project.ingest_source(
                actor="author",
                source=PDF(path="individual.pdf"),
                name="individual",
                idempotency_key="individual-key",
            ),
        )
    assert tuple(item.input.name for item in result.successes) == filenames[:2]
    assert _file_location(revision=single.revision) == "individual.pdf"
    assert reader.maximum == 1
    assert reader.active == 0
    with pytest.raises(ValueError, match="configured"):
        _ = await project.ingest_sources(
            actor="author",
            sources=selections,
            max_concurrent_sources=2,
        )


async def test_slow_file_processing_renews_its_lease_and_replays_exactly(
    tmp_path: Path,
    database_backend: DatabaseBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    now = datetime(2026, 11, 17, tzinfo=UTC)
    renewed = Event()
    real_renew = sqlalchemy_idempotency_repository.SqlAlchemyIdempotencyRepository.renew

    def clock() -> datetime:
        return now

    async def renew(
        self: sqlalchemy_idempotency_repository.SqlAlchemyIdempotencyRepository,
        *,
        invocation: Invocation,
        lease: Lease,
    ) -> Lease:
        receipt = await real_renew(self, invocation=invocation, lease=lease)
        renewed.set()
        return receipt

    class SlowParser(_TestParser):
        @override
        def parse(
            self, *, content: AcquiredSource, descriptor: FileDescriptor, limits: ProcessingLimits
        ) -> Iterator[ParsedChunk]:
            nonlocal now
            now += timedelta(seconds=45)
            _ = renewed.wait(timeout=0.25)
            now += timedelta(seconds=30)
            yield from super().parse(content=content, descriptor=descriptor, limits=limits)

    monkeypatch.setattr(
        sqlalchemy_idempotency_repository.SqlAlchemyIdempotencyRepository, "renew", renew
    )
    monkeypatch.setattr(
        "domain_kernel.sources.application.service._SOURCE_HEARTBEAT_SECONDS", 0.005, raising=False
    )
    _ = (tmp_path / "original.pdf").write_bytes(_FIRST_PDF)
    adapters = ClientIntegrations(
        transactions=database_backend.factory(clock=clock), format_parsers={"pdf": SlowParser()}
    )
    client = Client(config=database_backend.config, integrations=adapters)
    project = await client.create_project(actor="author", name="lease-test")
    requested = PDF(path="original.pdf", pages=[1])
    result = await project.ingest_source(
        actor="author",
        name="legislation",
        source=requested,
        idempotency_key="slow-file",
    )
    assert renewed.is_set()
    assert result.revision_id.value == Hashing.hash_bytes(content=_FIRST_PDF).value
    reopened = await Client(config=database_backend.config, integrations=adapters).get_project(
        name=project.name
    )
    assert (
        await reopened.ingest_source(
            actor="author",
            name="legislation",
            source=requested,
            idempotency_key="slow-file",
        )
        == result
    )
    assert len((await reopened.list_sources()).items) == 1
