"""Validate root-contained relative resource keys."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

from domain_kernel.shared.errors import SourceReadError
from domain_kernel.shared.validation import require_text


def relative_parts(*, path: str, allow_root: bool = False) -> tuple[str, ...]:
    """Resolve a safe scoped relative path without touching the filesystem."""
    require_text(value=path, field="Reader-relative path")
    selected = PurePosixPath(path)
    if (
        (not selected.parts and (not allow_root or path != "."))
        or selected.is_absolute()
        or PureWindowsPath(path).drive
        or ".." in selected.parts
        or "\\" in path
        or "\x00" in path
    ):
        raise SourceReadError(message="Select a relative path beneath the configured reader root.")
    return selected.parts
