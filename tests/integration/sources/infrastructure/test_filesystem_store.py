"""Verify filesystem artifact identity, containment, and declared metadata."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    ArtifactConflictError,
    ArtifactWrite,
    AttributeId,
    CollectionSemanticsObligation,
    DefinitionId,
    Iri,
    ModelId,
    ModelScope,
    ModelVersion,
    PinnedDefinitionReference,
    ProjectId,
    SemanticArtifactMetadata,
    SemanticGraphRole,
    SourceReadError,
)
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.sources.infrastructure.filesystem_store import FilesystemArtifactStore

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


def _write(*, content: bytes) -> ArtifactWrite:
    project = ProjectId(value="workspace")
    model = ModelId(value="recruitment")
    return ArtifactWrite(
        project_id=project,
        model_id=model,
        store="artifacts",
        key="projects/workspace/documents/model.ttl",
        media_type="text/turtle",
        expected_hash=hash_bytes(content=content),
    )


def test_same_bytes_different_metadata_conflict(tmp_path: Path) -> None:
    data = b"semantic graph bytes"
    write = _write(content=data)
    assert write.model_id is not None
    version = ModelVersion(
        scope=ModelScope(project_id=write.project_id, model_id=write.model_id),
        version="1.0.0",
        content_hash=write.expected_hash,
    )
    obligation = CollectionSemanticsObligation(
        owner=PinnedDefinitionReference(
            model=version,
            definition_id=DefinitionId(value="role"),
            definition_revision=1,
        ),
        attribute=AttributeId(value="identifiers"),
    )
    semantic = SemanticArtifactMetadata(
        model=version,
        graph_iri=Iri(value="https://example.org/recruitment/shapes"),
        role=SemanticGraphRole.INSTANCE_SHAPES,
        mapping_version="1",
    )
    supplied = [obligation]
    request = replace(write, semantic=semantic, consumer_obligations=supplied)
    supplied.clear()
    store = FilesystemArtifactStore(root=tmp_path, name="artifacts")
    actual = store.put(request=request, chunks=(data[:6], data[6:]))
    assert actual.consumer_obligations == (obligation,)
    assert actual.semantic == semantic
    restarted = FilesystemArtifactStore(root=tmp_path, name="artifacts")
    assert restarted.verify(artifact=actual)
    assert restarted.get(artifact=actual, max_bytes=len(data)) == data
    assert restarted.put(request=request, chunks=(data,)) == actual
    for alternate in (
        replace(request, consumer_obligations=()),
        replace(request, semantic=replace(semantic, mapping_version="2")),
        replace(request, media_type="text/plain"),
        replace(request, expected_hash=hash_bytes(content=b"different")),
    ):
        with pytest.raises(ArtifactConflictError):
            _ = restarted.put(request=alternate, chunks=(data,))
    assert restarted.get(artifact=actual, max_bytes=len(data)) == data
    _ = (tmp_path / actual.key).write_bytes(b"unexpected")
    assert not restarted.verify(artifact=actual)


def test_store_rejects_scope_escapes_and_linked_targets(tmp_path: Path) -> None:
    data = b"payload"
    write = _write(content=data)
    root = tmp_path / "store"
    scoped = root / "projects/workspace"
    scoped.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (scoped / "documents").symlink_to(outside, target_is_directory=True)
    store = FilesystemArtifactStore(root=root, name="artifacts")
    for key in (
        "projects/another-workspace/model.json",
        "projects/workspace/../model.json",
        write.key,
    ):
        with pytest.raises(SourceReadError):
            _ = store.put(request=replace(write, key=key), chunks=(data,))
    assert not list(outside.iterdir())
