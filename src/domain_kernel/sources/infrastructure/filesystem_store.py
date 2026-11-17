"""Publish immutable local artifact bytes through an atomic no-overwrite write."""

from __future__ import annotations

import asyncio
import os
import stat
from contextlib import ExitStack, contextmanager, suppress
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from domain_kernel._shared.domain.audit import Artifact
from domain_kernel.shared.errors import SourceReadError
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.sources.application.ports import OriginalStore
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.paths import relative_parts

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.identifiers.content_hash import ContentHash


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


def _link_at(*, directory: int, name: str, content: bytes) -> None:
    staged = f".write-{uuid4().hex}"
    descriptor = os.open(
        staged,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        mode=0o600,
        dir_fd=directory,
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            _ = output.write(content)
            output.flush()
            os.fsync(output.fileno())
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


def _write_portable(*, target: Path, content: bytes) -> None:
    staged = target.with_name(f".write-{uuid4().hex}")
    with staged.open("xb") as output:
        try:
            _ = output.write(content)
            output.flush()
            os.fsync(output.fileno())
            with suppress(FileExistsError):
                target.hardlink_to(staged)
        finally:
            # Windows requires a closed handle before deleting the temporary file.
            output.close()
            staged.unlink()


@final
class FilesystemArtifactStore(OriginalStore):
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
                        _link_at(directory=directory, name=parts[-1], content=content)
                    _read_at(
                        directory=directory,
                        name=parts[-1],
                        digest=digest,
                        byte_length=byte_length,
                    )
            else:
                target = _portable_target(root=self._root, parts=parts, create=create)
                if content is not None:
                    _write_portable(target=target, content=content)
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
