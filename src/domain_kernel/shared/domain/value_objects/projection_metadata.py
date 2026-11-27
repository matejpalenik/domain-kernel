"""Shared immutable metadata for payload, write request and artifact records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.value_objects.collection_semantics_obligation import (
    CollectionSemanticsObligation,
)
from domain_kernel.shared.domain.value_objects.key_enforcement_obligation import (
    KeyEnforcementObligation,
)
from domain_kernel.shared.domain.value_objects.reference_target_obligation import (
    ReferenceTargetObligation,
)
from domain_kernel.shared.domain.value_objects.relationship_enforcement_obligation import (
    RelationshipEnforcementObligation,
)
from domain_kernel.shared.domain.value_objects.schema_artifact_metadata import (
    SchemaArtifactMetadata,
)
from domain_kernel.shared.domain.value_objects.semantic_artifact_metadata import (
    SemanticArtifactMetadata,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.types.consumer_obligation import ConsumerObligation


_OBLIGATION_TYPES = (
    KeyEnforcementObligation,
    ReferenceTargetObligation,
    RelationshipEnforcementObligation,
    CollectionSemanticsObligation,
)


@dataclass(frozen=True, kw_only=True)
class ProjectionMetadata:
    """Shared immutable metadata for payload, write request and artifact records."""

    projection_limits: Sequence[str] = ()
    semantic: SemanticArtifactMetadata | None = None
    schema: SchemaArtifactMetadata | None = None
    consumer_obligations: Sequence[ConsumerObligation] = ()

    def __post_init__(self) -> None:
        """Snapshot the metadata without normalizing away meaningful content."""
        limits = SequenceValidation.snapshot_sequence(
            items=self.projection_limits, item_type=str, field="Projection limits"
        )

        for limit in limits:
            TextValidation.require_text(value=limit, field="Projection limit")

        object.__setattr__(self, "projection_limits", limits)

        if self.semantic is not None:
            RuntimeTypeValidation.require_exact(
                value=self.semantic, expected=SemanticArtifactMetadata, field="Semantic metadata"
            )

        if self.schema is not None:
            RuntimeTypeValidation.require_exact(
                value=self.schema, expected=SchemaArtifactMetadata, field="Schema metadata"
            )
            if self.semantic is not None:
                raise ValueError("Select either graph or schema projection metadata")

        if not SequenceValidation.is_non_string_sequence(value=self.consumer_obligations) or any(
            type(item) not in _OBLIGATION_TYPES for item in self.consumer_obligations
        ):
            raise TypeError("Use a sequence of typed consumer obligations")

        object.__setattr__(self, "consumer_obligations", tuple(self.consumer_obligations))
