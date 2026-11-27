"""Identity and verified digest of a scoped external artifact."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.domain.value_objects.projection_metadata import ProjectionMetadata
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation


@dataclass(frozen=True, kw_only=True)
class Artifact(ProjectionMetadata):
    """Identify a stored artifact and the exact bytes expected at its destination.

    Attributes:
        project_id: Project that owns the artifact.
        store: Configured store name within the project.
        key: Provider-relative destination within that store.
        content_hash: Digest of the exact stored bytes.
        model_id: Model scope, or None for a project-level artifact.
        provider_version: Opaque version assigned by the store, when available.
    """

    project_id: ProjectId
    store: str
    key: str
    content_hash: ContentHash
    model_id: ModelId | None = None
    provider_version: str | None = None

    def __post_init__(self) -> None:
        """Validate the artifact identity and any model-scoped projection metadata.

        Raises:
            ValueError: Projection metadata belongs to another scope or a location field is blank.
        """
        ProjectionMetadata.__post_init__(self)

        RuntimeTypeValidation.require_exact(
            value=self.project_id, expected=ProjectId, field="Artifact project"
        )
        if self.model_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.model_id, expected=ModelId, field="Artifact model"
            )

        RuntimeTypeValidation.require_exact(
            value=self.content_hash, expected=ContentHash, field="Artifact hash"
        )

        TextValidation.require_text(value=self.store, field="Artifact store")
        TextValidation.require_text(value=self.key, field="Artifact key")

        if self.semantic is not None and (
            self.semantic.model.scope.project_id != self.project_id
            or self.semantic.model.scope.model_id != self.model_id
        ):
            raise ValueError("Use semantic metadata from the artifact's model scope")

        if self.schema is not None and (
            self.schema.model.scope.project_id != self.project_id
            or self.schema.model.scope.model_id != self.model_id
        ):
            raise ValueError("Use schema metadata from the artifact's model scope")

        if self.provider_version is not None:
            TextValidation.require_text(
                value=self.provider_version, field="Artifact provider version"
            )
