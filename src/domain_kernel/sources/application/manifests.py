"""Verified frozen folder selections used by both batch and direct retries."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Runtime manifest schema.
from pathlib import PurePosixPath
from typing import Self

from pydantic import model_validator

from domain_kernel.configuration import ConfigurationModel
from domain_kernel.projects.domain.identifiers.project_id import ProjectId  # noqa: TC001 - Runtime manifest schema.
from domain_kernel.shared.contracts import Issue  # noqa: TC001 - Runtime manifest schema.
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.shared.identifiers.content_hash import ContentHash  # noqa: TC001 - Runtime manifest schema.
from domain_kernel.sources.application.contracts import (
    IngestionStage,
    SourceEntry,
    SourceEntryKind,
    SourceFolder,
    SourceInput,
)
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId  # noqa: TC001 - Runtime manifest schema.


class ManifestItem(ConfigurationModel):
    """One selected file or its structured planning issue."""

    file: SourceEntry
    input: SourceInput | None = None
    issue: Issue | None = None
    stage: IngestionStage | None = None

    @model_validator(mode="after")
    def _check_outcome(self) -> Self:
        if (self.input is None) == (self.issue is None):
            raise ValueError("Capture one resolved input or one selection issue")
        if self.input is not None:
            if (
                self.file.kind is not SourceEntryKind.FILE
                or self.input.source.resolved_location() != self.file.location
                or self.input.idempotency_key is None
                or self.stage is not None
            ):
                raise ValueError("Capture the exact selected file and generated key")
        elif self.stage is None:
            raise ValueError("Capture the stage of each selection issue")
        return self


class ManifestPayload(ConfigurationModel):
    """Immutable manifest data before its digest is attached."""

    id: SourceManifestId
    project_id: ProjectId
    provider_scope: str
    selection: SourceFolder
    actor: str
    request_hash: ContentHash
    created_at: datetime
    items: tuple[ManifestItem, ...]

    def fingerprint(self) -> ContentHash:
        """Hash the exact immutable selection metadata."""
        return hash_bytes(content=self.model_dump_json(exclude={"content_hash"}).encode())


class SourceManifest(ManifestPayload):
    """A complete durable selection with reproducible per-file acquisition guards."""

    content_hash: ContentHash

    @model_validator(mode="after")
    def _matches_content(self) -> Self:
        if self.content_hash != self.fingerprint() or self.created_at.utcoffset() is None:
            raise ValueError("Use the original complete manifest and its exact hash")
        origin = PurePosixPath(self.selection.location.path)
        paths: set[str] = set()
        keys: set[str] = set()
        for item in self.items:
            location = item.file.location
            if (
                location.reader != self.selection.location.reader
                or item.file.provider_scope != self.provider_scope
                or not PurePosixPath(location.path).is_relative_to(origin)
                or location.path in paths
            ):
                raise ValueError("Manifest files must belong to the exact scoped folder")
            paths.add(location.path)
            if item.input is not None:
                key = child_request_key(manifest_id=self.id, entry=item.file)
                if item.input.idempotency_key != key or key in keys:
                    raise ValueError("Retain the stable request key of every selected file")
                keys.add(key)
        return self


def child_request_key(*, manifest_id: SourceManifestId, entry: SourceEntry) -> str:
    """Bind one child request to its manifest and exact selected provider entry."""
    return hash_json(
        value=(
            "source-manifest-entry-v1",
            manifest_id.value,
            entry.provider_scope,
            entry.location.path,
            entry.provider_item_id,
            entry.provider_version,
        )
    ).value
