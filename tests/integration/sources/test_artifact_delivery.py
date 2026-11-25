"""Verify that delivery uses exact stored revisions and leaves publication independent."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from domain_kernel import (
    PDF,
    Accept,
    ArtifactConflictError,
    AuditAction,
    AuditOutcome,
    BundleId,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    CopyTo,
    DomainModelBuilder,
    DomainModelBundle,
    InvalidBundleError,
    ModelKind,
    ScopeMismatchError,
    SourceReadError,
    SourceRevisionMismatchError,
    StaleStateError,
)
from domain_kernel._shared.infrastructure.sqlite_operations import SQLiteIdempotencyRepository
from domain_kernel.configuration import FilesystemReader
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.sources.infrastructure.filesystem_store import FilesystemArtifactStore

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from domain_kernel import Artifact, ArtifactWrite, Model
    from domain_kernel._shared.application.persistence import Invocation, Lease
    from tests.support.persistence.database_backend import DatabaseBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def release(tmp_path: Path) -> tuple[Model, DomainModelBundle]:
    return await _release(client=Client(config=ClientConfiguration(base_dir=tmp_path)))


async def _release(*, client: Client) -> tuple[Model, DomainModelBundle]:
    project = await client.create_project(actor="author", name="recruitment")
    model = await project.create_model(
        actor="author", kind=ModelKind.OBSERVED, name="observed", description="Recruitment."
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_concept(name="actor", meaning="A recruitment actor.")
    plan = builder.build_change_plan(reason="Review recruitment actor.")
    proposal = await model.propose_change_plan(actor="author", plan=plan)
    _ = await model.decide_review(
        actor="reviewer", case=proposal, decision=Accept(reason="Agreed.")
    )
    prepared = await model.prepare_publication(actor="publisher")
    bundle = await model.publish(
        publication=prepared, version="1.0.0", actor="publisher", reason="Release."
    )
    return model, bundle


async def test_slow_artifact_write_keeps_its_lease_without_holding_a_transaction(
    database_backend: DatabaseBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 11, 17, tzinfo=UTC)
    renewed = Event()
    write = FilesystemArtifactStore.put
    real_renew = SQLiteIdempotencyRepository.renew

    def clock() -> datetime:
        return now

    def slow_write(
        self: FilesystemArtifactStore, *, request: ArtifactWrite, chunks: Iterable[bytes]
    ) -> Artifact:
        nonlocal now
        now += timedelta(seconds=45)
        _ = renewed.wait(timeout=0.25)
        now += timedelta(seconds=30)
        return write(self, request=request, chunks=chunks)

    async def renew(
        self: SQLiteIdempotencyRepository, *, invocation: Invocation, lease: Lease
    ) -> Lease:
        updated = await real_renew(self, invocation=invocation, lease=lease)
        renewed.set()
        return updated

    model, bundle = await _release(
        client=Client(
            config=database_backend.config,
            integrations=ClientIntegrations(transactions=database_backend.factory(clock=clock)),
        )
    )
    monkeypatch.setattr(FilesystemArtifactStore, "put", slow_write)
    monkeypatch.setattr(SQLiteIdempotencyRepository, "renew", renew)
    monkeypatch.setattr(
        "domain_kernel._shared.application.artifact_delivery._HEARTBEAT_SECONDS",
        0.005,
        raising=False,
    )
    artifact = await model.export(
        actor="publisher",
        bundle=bundle,
        store="artifacts",
        path="slow.json",
        idempotency_key="slow",
    )
    assert renewed.is_set()
    assert artifact.content_hash == hash_bytes(content=bundle.serialize())
    assert await model.get_version(version=bundle.version) == bundle


async def test_export_canonical_bytes_under_any_suffix(
    release: tuple[Model, DomainModelBundle], tmp_path: Path
) -> None:
    model, bundle = release
    artifact = await model.export(
        actor="publisher",
        bundle=bundle,
        store="artifacts",
        path="recruitment.txt",
        idempotency_key="transfer",
    )
    root = tmp_path / ".domain-kernel/artifacts"
    emitted = (root / artifact.key).read_bytes()
    assert emitted == bundle.serialize()
    assert artifact.content_hash == hash_bytes(content=emitted)
    assert (
        DomainModelBundle.deserialize(payload=emitted, expected_hash=artifact.content_hash)
        == bundle
    )
    assert (
        await model.export(
            actor="publisher",
            bundle=bundle,
            store="artifacts",
            path="recruitment.txt",
            idempotency_key="transfer",
        )
        == artifact
    )
    outcomes = [
        entry
        for entry in (await model.get_audit_history()).items
        if entry.action is AuditAction.EXPORT
    ]
    assert [entry.outcome for entry in outcomes] == [AuditOutcome.STARTED, AuditOutcome.SUCCEEDED]
    assert outcomes[1].after == (artifact,)


async def test_failed_artifact_write_can_resume_without_republishing(
    release: tuple[Model, DomainModelBundle], tmp_path: Path
) -> None:
    model, bundle = release
    root = tmp_path / ".domain-kernel/artifacts"
    _ = root.write_text("store unavailable")
    with pytest.raises(SourceReadError):
        _ = await model.export(
            actor="publisher",
            bundle=bundle,
            store="artifacts",
            path="recruitment.json",
            idempotency_key="safe-retry",
        )
    events = [
        entry
        for entry in (await model.get_audit_history()).items
        if entry.action is AuditAction.EXPORT
    ]
    assert events
    assert all(entry.outcome is not AuditOutcome.SUCCEEDED for entry in events)
    assert all(not entry.after for entry in events)
    assert await model.get_version(version=bundle.version) == bundle
    root.unlink()
    saved = await model.export(
        actor="publisher",
        bundle=bundle,
        store="artifacts",
        path="recruitment.json",
        idempotency_key="safe-retry",
    )
    assert (root / saved.key).read_bytes() == bundle.serialize()


async def test_foreign_export_never_creates_an_artifact_store(
    release: tuple[Model, DomainModelBundle], tmp_path: Path
) -> None:
    _, bundle = release
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(
        name="recruitment"
    )
    alternative = await project.create_model(
        actor="author", kind=ModelKind.OBSERVED, name="other", description="Other workspace."
    )
    with pytest.raises(ScopeMismatchError):
        _ = await alternative.export(
            actor="publisher", bundle=bundle, store="artifacts", path="invalid.json"
        )
    assert not (tmp_path / ".domain-kernel/artifacts").exists()


@pytest.mark.parametrize("missing", [False, True], ids=["changed-bytes", "missing-object"])
async def test_export_replay_requires_the_original_artifact(
    release: tuple[Model, DomainModelBundle], tmp_path: Path, *, missing: bool
) -> None:
    model, bundle = release
    artifact = await model.export(
        actor="publisher",
        bundle=bundle,
        store="artifacts",
        path="recruitment.json",
        idempotency_key="deliver-release",
    )
    stored = tmp_path / ".domain-kernel/artifacts" / artifact.key
    original = stored.read_bytes()
    if missing:
        stored.unlink()
    else:
        _ = stored.write_bytes(b"Not the released artifact.")
    before = await model.get_audit_history()

    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(
        name="recruitment"
    )
    reopened = await project.get_model(name="observed")
    with pytest.raises(ArtifactConflictError):
        _ = await reopened.export(
            actor="publisher",
            bundle=bundle,
            store="artifacts",
            path="recruitment.json",
            idempotency_key="deliver-release",
        )
    if missing:
        assert not stored.exists()
    else:
        assert stored.read_bytes() == b"Not the released artifact."
    assert await reopened.get_audit_history() == before
    assert await reopened.get_version(version=bundle.version) == bundle

    _ = stored.write_bytes(original)
    restored = await reopened.export(
        actor="publisher",
        bundle=bundle,
        store="artifacts",
        path="recruitment.json",
        idempotency_key="deliver-release",
    )
    assert restored == artifact
    assert await reopened.get_audit_history() == before


async def test_copy_checks_provenance_bytes_and_recovers_exact_completed_request(
    tmp_path: Path,
) -> None:
    source = tmp_path / "act.pdf"
    original = b"%PDF-1.7\n%original\n%%EOF"
    _ = source.write_bytes(original)
    project = await Client(
        config=ClientConfiguration(
            base_dir=tmp_path, readers=[FilesystemReader(name="inputs", root=".")]
        )
    ).create_project(actor="author", name="recruitment")
    captured = await project.ingest_source(actor="author", source=PDF(path="act.pdf"), name="act")
    revision = captured.revision
    destination = CopyTo(store="artifacts")
    with pytest.raises(SourceRevisionMismatchError):
        _ = await project.copy_source_original(
            actor="author",
            revision=replace(revision, byte_length=revision.byte_length + 1),
            destination=destination,
        )
    result = await project.copy_source_original(
        actor="author",
        revision=revision,
        destination=destination,
        idempotency_key="archive",
    )
    assert result.verified_hash == hash_bytes(content=original)
    assert (tmp_path / ".domain-kernel/artifacts" / result.artifact.key).read_bytes() == original
    _ = source.write_bytes(b"%PDF-1.7\n%changed\n%%EOF")
    with pytest.raises(SourceRevisionMismatchError):
        _ = await project.copy_source_original(
            actor="author", revision=revision, destination=destination
        )
    source.unlink()
    assert (
        await project.copy_source_original(
            actor="author",
            revision=revision,
            destination=destination,
            idempotency_key="archive",
        )
        == result
    )


async def test_forged_release_is_rejected_before_writing(
    release: tuple[Model, DomainModelBundle],
    tmp_path: Path,
) -> None:
    model, bundle = release
    forged = replace(bundle, id=BundleId(value="another-bundle"))
    with pytest.raises((InvalidBundleError, StaleStateError)):
        _ = await model.export(
            actor="publisher", bundle=forged, store="artifacts", path="forged.json"
        )
    assert not (tmp_path / ".domain-kernel/artifacts").exists()


async def test_cancellation_after_external_write_can_verify_and_acknowledge_same_artifact(
    release: tuple[Model, DomainModelBundle],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, bundle = release
    entered = Event()
    unblock = Event()
    put = FilesystemArtifactStore.put

    def pause_after_write(
        self: FilesystemArtifactStore,
        *,
        request: ArtifactWrite,
        chunks: Iterable[bytes],
    ) -> Artifact:
        result = put(self, request=request, chunks=chunks)
        entered.set()
        if not unblock.wait(timeout=5):
            raise TimeoutError("Test has not released the provider")
        return result

    monkeypatch.setattr(FilesystemArtifactStore, "put", pause_after_write)
    delivery = asyncio.create_task(
        model.export(
            actor="publisher",
            bundle=bundle,
            store="artifacts",
            path="cancelled.json",
            idempotency_key="resume-after-cancel",
        )
    )
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        _ = delivery.cancel()
        with pytest.raises(asyncio.CancelledError):
            _ = await delivery
        assert all(
            entry.outcome is not AuditOutcome.SUCCEEDED
            for entry in (await model.get_audit_history()).items
            if entry.action is AuditAction.EXPORT
        )
    finally:
        unblock.set()
    verified = await model.export(
        actor="publisher",
        bundle=bundle,
        store="artifacts",
        path="cancelled.json",
        idempotency_key="resume-after-cancel",
    )
    assert (tmp_path / ".domain-kernel/artifacts" / verified.key).read_bytes() == bundle.serialize()
    assert await model.get_version(version=bundle.version) == bundle
