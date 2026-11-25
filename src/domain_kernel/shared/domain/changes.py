"""Typed review effects and their comparison metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.reference_packs.domain.contracts import ReferenceAlignment
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.shared.contracts import ModelScope, ModelVersion
from domain_kernel.shared.domain.definitions import Definition
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import SnapshotReference


@unique
class Compatibility(StrEnum):
    """Effect of a change on the declared business contract."""

    INITIAL = "initial"
    COMPATIBLE = "compatible"
    BREAKING = "breaking"
    UNDETERMINED = "undetermined"


@unique
class ComparisonKind(StrEnum):
    """Snapshots compared when observing model effects."""

    PROPOSAL = "proposal"
    REVISION = "revision"
    BASELINE = "baseline"
    INITIAL = "initial"


@dataclass(frozen=True, kw_only=True)
class DefinitionChange:
    """Exact revisions on either side of one prospective change."""

    kind: DefinitionChangeKind
    before: Sequence[Definition]
    after: Sequence[Definition]
    evidence: tuple[()] = ()

    def __post_init__(self) -> None:
        """Detach both sides of the change."""
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=DefinitionChangeKind, field="Definition change kind"
        )
        object.__setattr__(
            self,
            "before",
            SequenceValidation.snapshot_sequence(
                items=self.before, item_type=Definition, field="Before revisions"
            ),
        )
        object.__setattr__(
            self,
            "after",
            SequenceValidation.snapshot_sequence(
                items=self.after, item_type=Definition, field="After revisions"
            ),
        )


@unique
class SourceDisposition(StrEnum):
    """Review disposition of one source occurrence."""

    MAPPED = "mapped"
    EXCLUDED = "excluded"
    UNRESOLVED = "unresolved"
    STALE = "stale"


@unique
class ReferenceDispositionKind(StrEnum):
    """Review disposition of a definition against its selected reference context."""

    MAPPED = "mapped"
    LOCAL_EXTENSION = "local_extension"
    EXCLUDED = "excluded"
    UNRESOLVED = "unresolved"
    STALE = "stale"


@dataclass(frozen=True, kw_only=True)
class SourceAlignment:
    """A version-qualified source occurrence disposition."""

    proposal_id: ProposalId
    definition_id: DefinitionId | None
    definition_revision: int | None
    disposition: SourceDisposition
    decision_id: DecisionId | None
    rationale: str
    context_fingerprint: str
    evidence: Sequence[Evidence] = ()

    def __post_init__(self) -> None:
        """Require exact disposition, occurrence and context metadata."""
        RuntimeTypeValidation.require_exact(
            value=self.proposal_id, expected=ProposalId, field="Proposal ID"
        )
        RuntimeTypeValidation.require_exact(
            value=self.disposition, expected=SourceDisposition, field="Disposition"
        )
        TextValidation.require_text(value=self.rationale, field="Alignment rationale")
        TextValidation.require_text(value=self.context_fingerprint, field="Alignment context")
        if self.definition_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.definition_id, expected=DefinitionId, field="Definition ID"
            )
        if self.definition_revision is not None:
            RuntimeTypeValidation.require_exact(
                value=self.definition_revision, expected=int, field="Definition revision"
            )
            if self.definition_revision < 1 or self.definition_id is None:
                raise ValueError("An alignment revision must pin an existing definition identity")
        if self.decision_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.decision_id, expected=DecisionId, field="Decision ID"
            )
        object.__setattr__(
            self,
            "evidence",
            SequenceValidation.snapshot_sequence(
                items=self.evidence, item_type=Evidence, field="Alignment evidence"
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ReferenceDisposition:
    """A definition's disposition with its original reviewed rationale."""

    definition_id: DefinitionId
    disposition: ReferenceDispositionKind
    decision_id: DecisionId | None
    rationale: str

    definition_revision: int | None = None
    reference_pack: ReferencePackPin | None = None
    alignment: ReferenceAlignment | None = None

    def __post_init__(self) -> None:
        """Preserve the exact identity and closed disposition kind."""
        RuntimeTypeValidation.require_exact(
            value=self.definition_id, expected=DefinitionId, field="Definition ID"
        )
        RuntimeTypeValidation.require_exact(
            value=self.disposition, expected=ReferenceDispositionKind, field="Disposition"
        )
        TextValidation.require_text(value=self.rationale, field="Disposition rationale")
        if self.decision_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.decision_id, expected=DecisionId, field="Decision ID"
            )

        if self.definition_revision is not None:
            RuntimeTypeValidation.require_exact(
                value=self.definition_revision, expected=int, field="Reviewed local revision"
            )
            if self.definition_revision < 1:
                raise ValueError("An alignment pins an exact positive local revision")
        if self.reference_pack is not None:
            RuntimeTypeValidation.require_exact(
                value=self.reference_pack, expected=ReferencePackPin, field="Disposition pack"
            )
        if self.alignment is not None:
            RuntimeTypeValidation.require_exact(
                value=self.alignment, expected=ReferenceAlignment, field="Reviewed alignment"
            )
            if self.alignment.reference_pack != self.reference_pack:
                raise ValueError("Use the disposition's exact reference pack")


@dataclass(frozen=True, kw_only=True)
class SourceAlignmentChange:
    """Before and after state of one reviewed source alignment."""

    before: SourceAlignment | None
    after: SourceAlignment | None


@dataclass(frozen=True, kw_only=True)
class ReferenceDispositionChange:
    """Before and after state of one reviewed reference disposition."""

    before: ReferenceDisposition | None
    after: ReferenceDisposition | None


@dataclass(frozen=True, kw_only=True)
class DefinitionCorrespondence:
    """Exact pre-change and post-change definition identities."""

    before_id: DefinitionId
    after_id: DefinitionId


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
