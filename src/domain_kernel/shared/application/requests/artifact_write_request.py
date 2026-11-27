from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.value_objects.projection_metadata import ProjectionMetadata
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.identifiers.model_id import ModelId
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.identifiers.content_hash import ContentHash


@dataclass(frozen=True, kw_only=True)
class ArtifactWriteRequest(ProjectionMetadata):
    """Request an immutable scoped destination for an exact payload."""

    project_id: ProjectId
    model_id: ModelId | None
    store: str
    key: str
    media_type: str
    expected_hash: ContentHash

    def __post_init__(self) -> None:
        """Validate the request using the same metadata rules as the resulting artifact."""
        ProjectionMetadata.__post_init__(self)

        _ = self.to_artifact()
        TextValidation.require_text(value=self.media_type, field="Artifact media type")

    def to_artifact(self, *, provider_version: str | None = None) -> Artifact:
        """Build the artifact descriptor from this write request.

        Args:
            provider_version: The version token supplied by the store, if available.

        Returns:
            The scoped destination, expected content hash, and projection metadata
            as an artifact descriptor.
        """
        return Artifact(
            project_id=self.project_id,
            model_id=self.model_id,
            store=self.store,
            key=self.key,
            content_hash=self.expected_hash,
            provider_version=provider_version,
            projection_limits=self.projection_limits,
            semantic=self.semantic,
            schema=self.schema,
            consumer_obligations=self.consumer_obligations,
        )
