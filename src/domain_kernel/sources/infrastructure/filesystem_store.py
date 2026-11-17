"""Publish immutable local artifact bytes through an atomic no-overwrite write."""

from __future__ import annotations

import asyncio
import os
import stat
from contextlib import ExitStack, contextmanager, suppress
from hashlib import sha256
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from domain_kernel._shared.application.artifacts import ArtifactStore, ArtifactWrite
from domain_kernel._shared.domain.artifact_conflict_error import ArtifactConflictError
from domain_kernel._shared.domain.audit import Artifact
from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel.shared.errors import ResourceLimitError, SourceReadError
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.sources.application.ports import OriginalStore, ReadableOriginalStore
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.paths import relative_parts

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable
    from pathlib import Path
    from typing import BinaryIO

    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.identifiers.content_hash import ContentHash
    from domain_kernel.sources.domain.models import SourceRevision


def _verify_descriptor(*, descriptor: int, digest: ContentHash, byte_length: int) -> None:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != byte_length:
        raise SourceRevisionMismatchError
    with os.fdopen(descriptor, "rb", closefd=False) as source:
        content = source.read(byte_length + 1)
    if hash_bytes(content=content) != digest:
        raise SourceRevisionMismatchError


@contextmanager
def _directory(*, root: Path, parts: tuple[str, ...], create: bool) -> Generator[int]:
    if create:
        root.mkdir(parents=True, exist_ok=True)
    with ExitStack() as close_fds:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        _ = close_fds.callback(os.close, directory)
        for name in parts:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(name, mode=0o700, dir_fd=directory)
            directory = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory,
            )
            _ = close_fds.callback(os.close, directory)
        yield directory


def _read_at(*, directory: int, name: str, digest: ContentHash, byte_length: int) -> None:
    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        _verify_descriptor(descriptor=source, digest=digest, byte_length=byte_length)
    finally:
        os.close(source)


def _write_chunks(
    *,
    output: BinaryIO,
    chunks: Iterable[bytes],
    digest: ContentHash,
) -> None:
    computed = sha256()
    for chunk in chunks:
        if type(chunk) is not bytes:
            raise TypeError("Supply exact byte chunks")
        computed.update(chunk)
        _ = output.write(chunk)
    if f"sha256:{computed.hexdigest()}" != digest.value:
        raise SourceRevisionMismatchError
    output.flush()
    os.fsync(output.fileno())


def _link_at(
    *,
    directory: int,
    name: str,
    chunks: Iterable[bytes],
    digest: ContentHash,
) -> None:
    staged = f".write-{uuid4().hex}"
    descriptor = os.open(
        staged,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        mode=0o600,
        dir_fd=directory,
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            _write_chunks(output=output, chunks=chunks, digest=digest)
        with suppress(FileExistsError):
            os.link(
                staged,
                name,
                src_dir_fd=directory,
                dst_dir_fd=directory,
                follow_symlinks=False,
            )
    finally:
        os.unlink(staged, dir_fd=directory)


def _portable_target(*, root: Path, parts: tuple[str, ...], create: bool) -> Path:
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or root.is_junction():
        raise SourceReadError(message="Select an approved store without links.")
    origin = root.resolve(strict=True)
    parent = origin
    for name in parts[:-1]:
        parent /= name
        if create:
            parent.mkdir(exist_ok=True)
        if parent.is_symlink() or parent.is_junction():
            raise SourceReadError(message="Select an approved store without links.")
    if not parent.resolve(strict=True).is_relative_to(origin):
        raise SourceReadError(message="Keep the artifact beneath the configured store.")
    target = parent / parts[-1]
    if target.is_symlink() or target.is_junction():
        raise SourceReadError(message="Use a regular artifact path without links.")
    return target


def _write_portable(
    *,
    target: Path,
    chunks: Iterable[bytes],
    digest: ContentHash,
) -> None:
    staged = target.with_name(f".write-{uuid4().hex}")
    with staged.open("xb") as output:
        try:
            _write_chunks(output=output, chunks=chunks, digest=digest)
            with suppress(FileExistsError):
                target.hardlink_to(staged)
        finally:
            # Windows requires a closed handle before deleting the temporary file.
            output.close()
            staged.unlink()


@final
class FilesystemOriginalStore(OriginalStore, ReadableOriginalStore):
    """Verify immutable copies without leaking provider or host-path details."""

    def __init__(self, *, root: Path, name: str) -> None:
        """Bind a destination without writing to it."""
        self._root = root
        self._name = name
        self._scope = hash_json(value=("filesystem-store", name, str(root))).value

    @property
    @override
    def provider_scope(self) -> str:
        return self._scope

    def _ensure(
        self,
        *,
        key: str,
        digest: ContentHash,
        byte_length: int,
        content: bytes | None,
    ) -> bool:
        parts = relative_parts(path=key)
        create = content is not None
        try:
            if os.open in os.supports_dir_fd and os.link in os.supports_dir_fd:
                with _directory(root=self._root, parts=parts[:-1], create=create) as directory:
                    if content is not None:
                        _link_at(
                            directory=directory, name=parts[-1], chunks=(content,), digest=digest
                        )
                    _read_at(
                        directory=directory,
                        name=parts[-1],
                        digest=digest,
                        byte_length=byte_length,
                    )
            else:
                target = _portable_target(root=self._root, parts=parts, create=create)
                if content is not None:
                    _write_portable(target=target, chunks=(content,), digest=digest)
                selected = target.lstat()
                with target.open("rb") as source:
                    if not os.path.samestat(selected, os.fstat(source.fileno())):
                        raise SourceRevisionMismatchError
                    _verify_descriptor(
                        descriptor=source.fileno(),
                        digest=digest,
                        byte_length=byte_length,
                    )
        except FileNotFoundError:
            if not create:
                return False
            raise SourceReadError(message="Check the selected artifact store.") from None
        except OSError:
            raise SourceReadError(message="Check access to the selected artifact store.") from None
        return True

    @override
    async def verify(
        self,
        *,
        project_id: ProjectId,
        key: str,
        digest: ContentHash,
        byte_length: int,
    ) -> Artifact | None:
        if not await asyncio.to_thread(
            self._ensure,
            key=key,
            digest=digest,
            byte_length=byte_length,
            content=None,
        ):
            return None
        return Artifact(project_id=project_id, store=self._name, key=key, content_hash=digest)

    @override
    async def put(
        self,
        *,
        project_id: ProjectId,
        key: str,
        content: bytes,
        digest: ContentHash,
    ) -> Artifact:
        if hash_bytes(content=content) != digest:
            raise SourceRevisionMismatchError
        _ = await asyncio.to_thread(
            self._ensure,
            key=key,
            digest=digest,
            byte_length=len(content),
            content=content,
        )
        return Artifact(project_id=project_id, store=self._name, key=key, content_hash=digest)

    def _read_original(self, *, key: str, max_bytes: int) -> bytes | None:
        try:
            with _read_file(root=self._root, parts=relative_parts(path=key)) as source:
                content = source.read(max_bytes + 1)
        except FileNotFoundError:
            return None
        except OSError:
            raise SourceReadError(message="Check access to the retained original store.") from None
        if len(content) > max_bytes:
            raise ResourceLimitError
        return content

    @override
    async def read_original(
        self,
        *,
        key: str,
        revision: SourceRevision,
        max_bytes: int,
    ) -> bytes | None:
        """Read the recorded immutable original and check its exact byte identity."""
        content = await asyncio.to_thread(self._read_original, key=key, max_bytes=max_bytes)
        if content is not None and (
            len(content) != revision.byte_length
            or hash_bytes(content=content).value != revision.revision_id.value
        ):
            raise SourceRevisionMismatchError
        return content


_MAX_METADATA_BYTES = 4 * 1024 * 1024
_BLOCK_BYTES = 64 * 1024


def _project_key_parts(*, project_id: ProjectId, key: str) -> tuple[str, ...]:
    parts = relative_parts(path=key)
    scope = ("projects", project_id.value)
    if (
        len(parts) <= len(scope)
        or parts[: len(scope)] != scope
        or "/".join(parts) != key
        or any(":" in part for part in parts)
    ):
        raise SourceReadError(message="Use a canonical key beneath the artifact's project.")
    return parts


@contextmanager
def _read_file(*, root: Path, parts: tuple[str, ...]) -> Generator[BinaryIO]:
    if os.open in os.supports_dir_fd:
        with _directory(root=root, parts=parts[:-1], create=False) as directory:
            descriptor = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
            with os.fdopen(descriptor, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise ArtifactConflictError
                yield source
    else:
        target = _portable_target(root=root, parts=parts, create=False)
        selected = target.lstat()
        if not stat.S_ISREG(selected.st_mode):
            raise ArtifactConflictError
        with target.open("rb") as source:
            if not os.path.samestat(selected, os.fstat(source.fileno())):
                raise ArtifactConflictError
            yield source


def _write_file(
    *,
    root: Path,
    parts: tuple[str, ...],
    chunks: Iterable[bytes],
    digest: ContentHash,
) -> None:
    if os.open in os.supports_dir_fd and os.link in os.supports_dir_fd:
        with _directory(root=root, parts=parts[:-1], create=True) as directory:
            _link_at(directory=directory, name=parts[-1], chunks=chunks, digest=digest)
    else:
        target = _portable_target(root=root, parts=parts, create=True)
        _write_portable(target=target, chunks=chunks, digest=digest)


@final
class FilesystemArtifactStore(ArtifactStore):
    """Write a project-scoped payload with immutable request metadata."""

    def __init__(self, *, root: Path, name: str) -> None:
        """Bind the configured directory without touching the store."""
        self._root = root
        self._name = name
        self.provider_scope = hash_json(value=("filesystem-artifacts", name, str(root))).value

    def _paths(self, *, artifact: Artifact) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if artifact.store != self._name:
            raise ArtifactConflictError
        parts = _project_key_parts(project_id=artifact.project_id, key=artifact.key)
        return parts, (".domain-kernel-artifact-metadata", *parts)

    def _metadata(self, *, parts: tuple[str, ...]) -> bytes:
        with _read_file(root=self._root, parts=parts) as source:
            stored = source.read(_MAX_METADATA_BYTES + 1)
        if len(stored) > _MAX_METADATA_BYTES:
            raise ArtifactConflictError
        return stored

    @override
    def put(self, *, request: ArtifactWrite, chunks: Iterable[bytes]) -> Artifact:
        metadata = record_bytes(value=request, root_type=ArtifactWrite)
        metadata_hash = hash_bytes(content=metadata)
        artifact = request.artifact(provider_version=metadata_hash.value)
        parts, metadata_path = self._paths(artifact=artifact)
        if len(metadata) > _MAX_METADATA_BYTES:
            raise ResourceLimitError(message="Use artifact metadata within the store budget.")
        try:
            try:
                existing = self._metadata(parts=metadata_path)
            except FileNotFoundError:
                try:
                    with _read_file(root=self._root, parts=parts):
                        try:
                            existing = self._metadata(parts=metadata_path)
                        except FileNotFoundError:
                            raise ArtifactConflictError from None
                except FileNotFoundError:
                    _write_file(
                        root=self._root,
                        parts=metadata_path,
                        chunks=(metadata,),
                        digest=metadata_hash,
                    )
                    existing = self._metadata(parts=metadata_path)
            if existing != metadata:
                raise ArtifactConflictError
            _write_file(root=self._root, parts=parts, chunks=chunks, digest=artifact.content_hash)
            if not self.verify(artifact=artifact):
                raise ArtifactConflictError
        except OSError:
            raise SourceReadError(message="Check access to the selected artifact store.") from None
        except SourceRevisionMismatchError:
            raise ArtifactConflictError from None
        return artifact

    def _check_metadata(self, *, artifact: Artifact, parts: tuple[str, ...]) -> None:
        metadata = self._metadata(parts=parts)
        try:
            request = read_record(content=metadata, expected=ArtifactWrite, root_type=ArtifactWrite)
        except (TypeError, ValueError):
            raise ArtifactConflictError from None
        if request.artifact(provider_version=hash_bytes(content=metadata).value) != artifact:
            raise ArtifactConflictError

    @override
    def get(self, *, artifact: Artifact, max_bytes: int) -> bytes:
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("Set a positive artifact read limit")
        parts, metadata = self._paths(artifact=artifact)
        try:
            self._check_metadata(artifact=artifact, parts=metadata)
            with _read_file(root=self._root, parts=parts) as source:
                content = source.read(max_bytes + 1)
        except OSError:
            raise SourceReadError(
                message="Open the exact artifact in the configured store."
            ) from None
        if len(content) > max_bytes:
            raise ResourceLimitError(message="Use an artifact within the requested byte limit.")
        if hash_bytes(content=content) != artifact.content_hash:
            raise ArtifactConflictError
        return content

    @override
    def verify(self, *, artifact: Artifact) -> bool:
        parts, metadata = self._paths(artifact=artifact)
        try:
            self._check_metadata(artifact=artifact, parts=metadata)
            digest = sha256()
            with _read_file(root=self._root, parts=parts) as source:
                while block := source.read(_BLOCK_BYTES):
                    digest.update(block)
        except (FileNotFoundError, ArtifactConflictError):
            return False
        except OSError:
            raise SourceReadError(message="Check access to the selected artifact store.") from None
        return artifact.content_hash.value == f"sha256:{digest.hexdigest()}"
