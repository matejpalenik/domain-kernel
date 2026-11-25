"""Reader-relative POSIX locations and case-sensitive selection patterns."""

from __future__ import annotations

from pathlib import PurePosixPath

from domain_kernel.shared.domain.validators.paths import relative_parts

__all__ = ["matches_globs", "relative_parts", "require_glob"]


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
