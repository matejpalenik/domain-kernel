"""Verify that delivery uses exact stored revisions and leaves publication independent."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from threading import Event
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from domain_kernel import (
    PDF,
    Accept,
    AuditAction,
    AuditOutcome,
    BundleId,
    Client,
    ClientConfiguration,
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
from domain_kernel.configuration import FilesystemReader
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.sources.infrastructure.filesystem_store import FilesystemArtifactStore

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from domain_kernel import Artifact, ArtifactWrite, Model

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def release(tmp_path: Path) -> tuple[Model, DomainModelBundle]:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author", name="recruitment"
    )
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
