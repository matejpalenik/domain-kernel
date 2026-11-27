"""Capture the caller's intent to create a project."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class CreateProject:
    """The inputs for one project creation request."""

    actor: str
    display_name: str | None
    name: str | None
