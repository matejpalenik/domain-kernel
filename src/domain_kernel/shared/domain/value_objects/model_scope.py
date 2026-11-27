from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId


@dataclass(frozen=True, kw_only=True)
class ModelScope:
    """Project and model identity used to scope operations and references."""

    project_id: ProjectId
    model_id: ModelId

    def __post_init__(self) -> None:
        """Require the nominal project and model identity types."""
        if type(self.project_id) is not ProjectId:
            raise TypeError("ModelScope project_id must be a ProjectId")
        if type(self.model_id) is not ModelId:
            raise TypeError("ModelScope model_id must be a ModelId")
