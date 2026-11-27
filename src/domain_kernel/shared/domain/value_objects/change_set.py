"""The typed effects and compared scope for an inspected change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.enums.comparison_kind import ComparisonKind
from domain_kernel.shared.domain.enums.compatibility import Compatibility
from domain_kernel.shared.domain.value_objects.definition_change import DefinitionChange
from domain_kernel.shared.domain.value_objects.definition_correspondence import (
    DefinitionCorrespondence,
)
from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion
from domain_kernel.shared.domain.value_objects.reference_disposition_change import (
    ReferenceDispositionChange,
)
from domain_kernel.shared.domain.value_objects.source_alignment_change import SourceAlignmentChange
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.shared.domain.types.snapshot_reference import SnapshotReference


@dataclass(frozen=True, kw_only=True)
class ChangeSet:
    """The typed effects and compared scope for an inspected change."""

    scope: ModelScope
    changes: Sequence[DefinitionChange]
    compatibility: Compatibility
    comparison: ComparisonKind
    before: SnapshotReference | None = None
    after: SnapshotReference | None = None
    before_reference_pack: ReferencePackPin | None = None
    after_reference_pack: ReferencePackPin | None = None
    before_dependencies: Sequence[ModelVersion] = ()
    after_dependencies: Sequence[ModelVersion] = ()
    correspondences: Sequence[DefinitionCorrespondence] = ()
    source_alignment_changes: Sequence[SourceAlignmentChange] = ()
    reference_disposition_changes: Sequence[ReferenceDispositionChange] = ()

    def __post_init__(self) -> None:
        """Hold detached change records and exact declared comparison values."""
        RuntimeTypeValidation.require_exact(
            value=self.scope, expected=ModelScope, field="Change scope"
        )
        RuntimeTypeValidation.require_exact(
            value=self.compatibility, expected=Compatibility, field="Compatibility"
        )
        RuntimeTypeValidation.require_exact(
            value=self.comparison, expected=ComparisonKind, field="Comparison kind"
        )

        object.__setattr__(
            self,
            "changes",
            SequenceValidation.snapshot_sequence(
                items=self.changes, item_type=DefinitionChange, field="Changes"
            ),
        )
        object.__setattr__(
            self,
            "correspondences",
            SequenceValidation.snapshot_sequence(
                items=self.correspondences,
                item_type=DefinitionCorrespondence,
                field="Definition correspondences",
            ),
        )
        object.__setattr__(
            self,
            "source_alignment_changes",
            SequenceValidation.snapshot_sequence(
                items=self.source_alignment_changes,
                item_type=SourceAlignmentChange,
                field="Source alignment changes",
            ),
        )
        object.__setattr__(
            self,
            "reference_disposition_changes",
            SequenceValidation.snapshot_sequence(
                items=self.reference_disposition_changes,
                item_type=ReferenceDispositionChange,
                field="Reference disposition changes",
            ),
        )
        object.__setattr__(
            self,
            "before_dependencies",
            SequenceValidation.snapshot_sequence(
                items=self.before_dependencies,
                item_type=ModelVersion,
                field="Before dependencies",
            ),
        )
        object.__setattr__(
            self,
            "after_dependencies",
            SequenceValidation.snapshot_sequence(
                items=self.after_dependencies,
                item_type=ModelVersion,
                field="After dependencies",
            ),
        )
