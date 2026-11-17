"""Reader-relative POSIX locations and case-sensitive selection patterns."""

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


def require_glob(*, pattern: str) -> None:
    """Reject escapes and require recursive globstars to occupy whole segments."""
    parts = relative_parts(path=pattern)
    if any("**" in part and part != "**" for part in parts):
        raise ValueError("Use ** as a complete glob segment")


def matches_globs(*, path: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    """Apply exact case-sensitive path filters with exclusions taking priority."""
    selected = PurePosixPath(path)
    return (
        not include or any(selected.full_match(pattern, case_sensitive=True) for pattern in include)
    ) and not any(selected.full_match(pattern, case_sensitive=True) for pattern in exclude)
