"""Acquire bounded file bytes beneath one explicitly approved root."""

from __future__ import annotations

import asyncio
import os
import stat
from base64 import urlsafe_b64decode, urlsafe_b64encode
from contextlib import ExitStack, asynccontextmanager, contextmanager
from datetime import UTC, datetime
from io import BytesIO
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, final, override

from domain_kernel.shared.contracts import Page
from domain_kernel.shared.errors import (
    ResourceLimitError,
    SourceNotFoundError,
    SourceReadError,
    StaleStateError,
)
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.sources.application.contracts import ReaderLocation, SourceEntry, SourceEntryKind
from domain_kernel.sources.application.ports import AcquiredSource, SeekableBytes, SourceReader
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.models import FileOrigin
from domain_kernel.sources.domain.paths import relative_parts

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator
    from pathlib import Path

    from domain_kernel.configuration import SourceSelectionLimits
    from domain_kernel.sources.domain.models import ProcessingLimits, SourceRevision


def _read_descriptor(*, descriptor: int, max_bytes: int) -> tuple[bytes, os.stat_result]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise SourceReadError(message="Supply a regular file in this reader.")
    if before.st_size > max_bytes:
        raise ResourceLimitError
    with os.fdopen(descriptor, "rb", closefd=False) as source:
        content = source.read(max_bytes + 1)
    after = os.fstat(descriptor)
    if len(content) > max_bytes:
        raise ResourceLimitError
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise StaleStateError(message="Inspect the selected file after the writer has finished.")
    return content, before


@contextmanager
def _directory(*, root: Path, parts: tuple[str, ...]) -> Generator[int]:
    """Hold every opened directory beneath the approved root until the operation finishes."""
    with ExitStack() as close_fds:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        _ = close_fds.callback(os.close, directory)
        for name in parts:
            directory = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory,
            )
            _ = close_fds.callback(os.close, directory)
        yield directory


def _read_relative(
    *,
    root: Path,
    parts: tuple[str, ...],
    max_bytes: int,
) -> tuple[bytes, os.stat_result]:
    with _directory(root=root, parts=parts[:-1]) as directory, ExitStack() as close_fds:
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        _ = close_fds.callback(os.close, descriptor)
        return _read_descriptor(descriptor=descriptor, max_bytes=max_bytes)


def _portable_path(*, root: Path, parts: tuple[str, ...]) -> Path:
    origin = root.resolve(strict=True)
    file = origin
    for name in parts:
        file /= name
        if file.is_symlink() or file.is_junction():
            raise SourceReadError(message="Select a path without intermediate links.")
    if not file.resolve(strict=True).is_relative_to(origin):
        raise SourceReadError(message="Select a path beneath the configured reader root.")
    return file


def _read_portable(
    *,
    root: Path,
    parts: tuple[str, ...],
    max_bytes: int,
) -> tuple[bytes, os.stat_result]:
    # Platforms without descriptor-relative opens still verify the opened file identity.
    file = _portable_path(root=root, parts=parts)
    selected = file.stat()
    if not stat.S_ISREG(selected.st_mode):
        raise SourceReadError(message="Select a regular file in this reader.")
    with file.open("rb") as source:
        if not os.path.samestat(selected, os.fstat(source.fileno())):
            raise StaleStateError(
                message="Inspect the selected file after the writer has finished."
            )
        return _read_descriptor(descriptor=source.fileno(), max_bytes=max_bytes)


def _identity(*, metadata: os.stat_result) -> str:
    return f"{metadata.st_dev}:{metadata.st_ino}"


def _version(*, metadata: os.stat_result) -> str:
    return f"{metadata.st_mtime_ns}:{metadata.st_ctime_ns}:{metadata.st_size}"


def _entry_kind(*, metadata: os.stat_result) -> SourceEntryKind:
    if stat.S_ISDIR(metadata.st_mode):
        return SourceEntryKind.FOLDER
    return SourceEntryKind.FILE if stat.S_ISREG(metadata.st_mode) else SourceEntryKind.LINK


def _cursor_after(*, cursor: PageCursor | None, binding: str) -> str:
    if cursor is None:
        return ""
    try:
        key, last = urlsafe_b64decode(cursor.value).decode("utf-8").split("\0", maxsplit=1)
        if key == binding and last:
            return last
    except ValueError:
        pass
    raise StaleStateError(message="Restart listing from the current exact folder selection.")


@final
class _Buffer(SeekableBytes):
    def __init__(self, *, data: BytesIO) -> None:
        self._data = data

    @override
    def read(self, *, size: int = -1) -> bytes:
        return self._data.read(size)

    @override
    def seek(self, *, offset: int, whence: int = 0) -> int:
        return self._data.seek(offset, whence)

    @override
    def tell(self) -> int:
        return self._data.tell()


@final
class FilesystemSourceReader(SourceReader):
    """Capture and enumerate approved local paths without following links."""

    def __init__(self, *, root: Path, name: str = "inputs") -> None:
        """Bind a configured root without performing file I/O."""
        self._root = root
        self._name = name
        self._scope = hash_json(value=("filesystem", name, str(root))).value

    @property
    @override
    def provider_scope(self) -> str:
        return self._scope

    async def read(self, *, relative_path: str, max_bytes: int) -> bytes:
        """Return the existing bounded asset-reader contract."""
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("Set a positive source byte limit")
        parts = relative_parts(path=relative_path)
        content, _ = await asyncio.to_thread(self._capture, parts=parts, max_bytes=max_bytes)
        return content

    def _capture(
        self,
        *,
        parts: tuple[str, ...],
        max_bytes: int,
    ) -> tuple[bytes, os.stat_result]:
        try:
            if os.open in os.supports_dir_fd:
                return _read_relative(root=self._root, parts=parts, max_bytes=max_bytes)
            return _read_portable(root=self._root, parts=parts, max_bytes=max_bytes)
        except FileNotFoundError:
            raise SourceNotFoundError from None
        except OSError:
            raise SourceReadError(
                message="Check reader access and use a regular file without links.",
            ) from None

    def _require_binding(self, *, location: ReaderLocation) -> None:
        if location.reader != self._name:
            raise SourceReadError(message="Select a location in this configured reader.")

    @override
    @asynccontextmanager
    async def open(
        self,
        *,
        location: ReaderLocation,
        limits: ProcessingLimits,
        expected: SourceRevision | None = None,
        expected_entry: SourceEntry | None = None,
    ) -> AsyncGenerator[AcquiredSource]:
        self._require_binding(location=location)
        content, metadata = await asyncio.to_thread(
            self._capture,
            parts=relative_parts(path=location.path),
            max_bytes=limits.max_source_bytes,
        )
        digest = hash_bytes(content=content)
        version = _version(metadata=metadata)
        if expected_entry is not None and (
            expected_entry.location != location
            or expected_entry.kind is not SourceEntryKind.FILE
            or expected_entry.provider_scope != self._scope
            or (
                expected_entry.provider_item_id is not None
                and expected_entry.provider_item_id != _identity(metadata=metadata)
            )
            or (
                expected_entry.provider_version is not None
                and expected_entry.provider_version != version
            )
        ):
            raise SourceRevisionMismatchError
        if expected is not None and (
            expected.origin.reader != location.reader
            or expected.origin.provider_scope != self._scope
            or expected.origin.location != location.path
            or expected.revision_id.value != digest.value
            or (
                expected.origin.provider_version is not None
                and expected.origin.provider_version != version
            )
        ):
            raise SourceRevisionMismatchError
        with BytesIO(content) as stream:
            yield AcquiredSource(
                stream=_Buffer(data=stream),
                origin=FileOrigin(
                    reader=self._name,
                    provider_scope=self._scope,
                    location=location.path,
                    provider_version=version,
                    acquired_at=datetime.now(tz=UTC),
                ),
                byte_length=len(content),
                content_hash=digest,
            )

    def _list(
        self,
        *,
        parts: tuple[str, ...],
        maximum: int,
    ) -> tuple[str, tuple[tuple[str, os.stat_result], ...]]:
        def inspect(
            *,
            origin: int | Path,
            before: os.stat_result,
        ) -> tuple[tuple[str, os.stat_result], ...]:
            entries: list[tuple[str, os.stat_result]] = []
            with os.scandir(origin) as children:
                for child in children:
                    if len(entries) == maximum:
                        raise ResourceLimitError(message="Select a smaller folder.")
                    entries.append((child.name, child.stat(follow_symlinks=False)))
            after = os.fstat(origin) if isinstance(origin, int) else origin.stat()
            if not os.path.samestat(before, after) or _version(metadata=before) != _version(
                metadata=after,
            ):
                raise StaleStateError(message="List the folder after its contents settle.")
            return tuple(sorted(entries, key=lambda item: item[0]))

        try:
            if os.open in os.supports_dir_fd and os.scandir in os.supports_fd:
                with _directory(root=self._root, parts=parts) as directory:
                    before = os.fstat(directory)
                    entries = inspect(origin=directory, before=before)
            else:
                folder = _portable_path(root=self._root, parts=parts)
                before = folder.stat()
                entries = inspect(origin=folder, before=before)
        except FileNotFoundError:
            raise SourceNotFoundError from None
        except OSError:
            raise SourceReadError(
                message="Check reader access and select a folder without links.",
            ) from None
        return f"{_identity(metadata=before)}:{_version(metadata=before)}", entries

    @override
    async def list_children(
        self,
        *,
        location: ReaderLocation,
        limits: SourceSelectionLimits,
        limit: int = 100,
        cursor: PageCursor | None = None,
    ) -> Page[SourceEntry]:
        self._require_binding(location=location)
        if type(limit) is not int or limit < 1:
            raise ValueError("Use a positive folder page size")
        version, entries = await asyncio.to_thread(
            self._list,
            parts=relative_parts(path=location.path, allow_root=True),
            maximum=limits.max_listing_entries,
        )
        binding = hash_json(value=(self._scope, location.path, version)).value
        after = _cursor_after(cursor=cursor, binding=binding)
        matched = [(name, metadata) for name, metadata in entries if name > after]
        selected = matched[:limit]
        continuation = None
        if len(matched) > limit:
            key = urlsafe_b64encode(f"{binding}\0{selected[-1][0]}".encode()).decode()
            continuation = PageCursor(value=key)
        return Page(
            items=tuple(
                SourceEntry(
                    location=ReaderLocation(
                        reader=self._name,
                        path=(PurePosixPath(location.path) / name).as_posix(),
                    ),
                    kind=_entry_kind(metadata=metadata),
                    provider_scope=self._scope,
                    provider_item_id=_identity(metadata=metadata),
                    provider_version=_version(metadata=metadata),
                )
                for name, metadata in selected
            ),
            next_cursor=continuation,
        )
