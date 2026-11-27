"""Loaded project catalog metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.domain.policies.lookup_naming_policy import LookupNamingPolicy
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

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
        RuntimeTypeValidation.require_exact(value=self.id, expected=ProjectId, field="Project ID")
        LookupNamingPolicy.require_lookup_name(name=self.name)
        TextValidation.require_text(value=self.display_name, field="Project display name")
        if self.created_at.utcoffset() is None:
            raise ValueError("Project creation time must include a time zone")
