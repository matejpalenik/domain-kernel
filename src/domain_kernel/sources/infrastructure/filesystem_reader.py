"""Acquire bounded file bytes beneath one explicitly approved root."""

from __future__ import annotations

import asyncio
import os
import stat
from contextlib import ExitStack
from pathlib import PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, final

from domain_kernel.shared.errors import (
    ResourceLimitError,
    SourceNotFoundError,
    SourceReadError,
    StaleStateError,
)
from domain_kernel.shared.validation import require_text

if TYPE_CHECKING:
    from pathlib import Path


def _relative_parts(*, path: str) -> tuple[str, ...]:
    require_text(value=path, field="Reader-relative path")
    selected = PurePosixPath(path)
    if (
        not selected.parts
        or selected.is_absolute()
        or PureWindowsPath(path).drive
        or ".." in selected.parts
        or "\\" in path
        or "\x00" in path
    ):
        raise SourceReadError(message="Select a relative file beneath the configured reader root.")
    return selected.parts


def _read_descriptor(*, descriptor: int, max_bytes: int) -> bytes:
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
    return content


def _read_relative(*, root: Path, parts: tuple[str, ...], max_bytes: int) -> bytes:
    # Bind traversal to open descriptors and reject links at every relative component.
    with ExitStack() as close_fds:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        _ = close_fds.callback(os.close, directory)
        for name in parts[:-1]:
            directory = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory,
            )
            _ = close_fds.callback(os.close, directory)
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        _ = close_fds.callback(os.close, descriptor)
        return _read_descriptor(descriptor=descriptor, max_bytes=max_bytes)


def _read_portable(*, root: Path, parts: tuple[str, ...], max_bytes: int) -> bytes:
    # Platforms without descriptor-relative opens still verify the opened file identity.
    origin = root.resolve(strict=True)
    file = origin
    for name in parts:
        file /= name
        if file.is_symlink() or file.is_junction():
            raise SourceReadError(message="Select a regular file without intermediate links.")
    selected = file.stat()
    if not stat.S_ISREG(selected.st_mode) or not file.resolve(strict=True).is_relative_to(origin):
        raise SourceReadError(message="Select a regular file beneath the configured reader root.")
    with file.open("rb") as source:
        if not os.path.samestat(selected, os.fstat(source.fileno())):
            raise StaleStateError(
                message="Inspect the selected file after the writer has finished."
            )
        return _read_descriptor(descriptor=source.fileno(), max_bytes=max_bytes)


@final
class FilesystemSourceReader:
    """Capture approved local files without exposing host paths in failures."""

    def __init__(self, *, root: Path) -> None:
        """Bind an approved root without performing file I/O."""
        self._root = root

    async def read(self, *, relative_path: str, max_bytes: int) -> bytes:
        """Return an immutable, bounded copy of the exact file bytes."""
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("Set a positive source byte limit")
        parts = _relative_parts(path=relative_path)
        return await asyncio.to_thread(self._capture, parts=parts, max_bytes=max_bytes)

    def _capture(self, *, parts: tuple[str, ...], max_bytes: int) -> bytes:
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
