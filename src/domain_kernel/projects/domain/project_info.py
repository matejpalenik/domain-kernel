"""Loaded project catalog metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.domain.naming import require_lookup_name
from domain_kernel.shared.validation import require_exact, require_text

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class ProjectInfo:
    """Detached stable project identity and creation metadata."""

    id: ProjectId
    name: str
    display_name: str
    created_at: datetime

    def __post_init__(self) -> None:
        """Require a stable name, display label and timestamp."""
        require_exact(value=self.id, expected=ProjectId, field="Project ID")
        require_lookup_name(name=self.name)
        require_text(value=self.display_name, field="Project display name")
        if self.created_at.utcoffset() is None:
            raise ValueError("Project creation time must include a time zone")
