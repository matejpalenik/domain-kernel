"""Immutable snapshots of the two business reconciliation layers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum, unique
from typing import TYPE_CHECKING

from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.reconciliation.domain.identifiers.alignment_suggestion_id import (
    AlignmentSuggestionId,
)
from domain_kernel.reference_packs.domain.contracts import MappingRelation
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.shared.contracts import ModelScope
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence


@unique
class AlignmentLayer(StrEnum):
    """The question a candidate suggestion addresses."""

    SOURCE_TO_MODEL = "source_to_model"
    MODEL_TO_REFERENCE = "model_to_reference"


@unique
class AlignmentStatus(StrEnum):
    """The checkpoint's review preparation state."""

    PROPOSED = "proposed"
    PREPARED = "prepared"


@dataclass(frozen=True, kw_only=True)
class AlignmentSuggestion:
    """A candidate target with its exact evidence and comparison context."""

    id: AlignmentSuggestionId
    scope: ModelScope
    layer: AlignmentLayer
    proposal_ids: Sequence[ProposalId]
    definition_id: DefinitionId
    definition_revision: int
    reference_id: ReferenceDefinitionId | None
    relation: MappingRelation | None
    evidence: Sequence[Evidence]
    reason: str
    context_fingerprint: str
    reused_decision_id: DecisionId | None = None

    def __post_init__(self) -> None:
        """Validate the layer and snapshot its exact source occurrences."""
        require_exact(value=self.id, expected=AlignmentSuggestionId, field="Suggestion ID")
        require_exact(value=self.scope, expected=ModelScope, field="Suggestion scope")
        require_exact(value=self.layer, expected=AlignmentLayer, field="Alignment layer")
        require_exact(value=self.definition_id, expected=DefinitionId, field="Local definition ID")
        require_exact(value=self.definition_revision, expected=int, field="Local revision")
        if self.definition_revision < 1:
            raise ValueError("Use a positive local revision")
        require_text(value=self.reason, field="Suggestion rationale")
        require_text(value=self.context_fingerprint, field="Comparison context")
        proposals = snapshot_sequence(
            items=self.proposal_ids, item_type=ProposalId, field="Occurrences"
        )
        evidence = snapshot_sequence(items=self.evidence, item_type=Evidence, field="Evidence")
        if len(proposals) != len(set(proposals)) or any(
            item.source.project_id != self.scope.project_id for item in evidence
        ):
            raise ValueError("Use distinct occurrences and evidence from this project")
        if self.layer is AlignmentLayer.SOURCE_TO_MODEL:
            if (
                self.reference_id is not None
                or self.relation is not None
                or not proposals
                or not evidence
            ):
                raise ValueError("Use cited occurrences and a local target for source alignment")
        else:
            require_exact(
                value=self.reference_id, expected=ReferenceDefinitionId, field="Reference ID"
            )
            if self.relation is not None:
                require_exact(
                    value=self.relation, expected=MappingRelation, field="Reviewed relation"
                )
            if self.relation is not None and self.reused_decision_id is None:
                raise ValueError("A recorded relation requires its reviewed decision")
        if self.reused_decision_id is not None:
            require_exact(
                value=self.reused_decision_id, expected=DecisionId, field="Reused decision"
            )
        object.__setattr__(self, "proposal_ids", proposals)
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True, kw_only=True)
class Alignment:
    """A checkpoint covering suggestions, unmatched occurrences and required gaps."""

    id: AlignmentId
    scope: ModelScope
    discovery_id: DiscoveryDraftId
    reference_pack: ReferencePackPin | None
    version: int
    status: AlignmentStatus
    suggestions: Sequence[AlignmentSuggestion]
    unmatched_proposal_ids: Sequence[ProposalId] = ()
    uncovered_reference_ids: Sequence[ReferenceDefinitionId] = ()

    def __post_init__(self) -> None:
        """Keep suggestions and missing coverage bound to the exact workspace."""
        require_exact(value=self.id, expected=AlignmentId, field="Alignment ID")
        require_exact(value=self.scope, expected=ModelScope, field="Alignment scope")
        require_exact(value=self.discovery_id, expected=DiscoveryDraftId, field="Discovery draft")
        require_exact(value=self.version, expected=int, field="Alignment version")
        require_exact(value=self.status, expected=AlignmentStatus, field="Alignment status")
        if self.version < 1:
            raise ValueError("Use a positive alignment version")
        if self.reference_pack is not None:
            require_exact(
                value=self.reference_pack, expected=ReferencePackPin, field="Reference pack"
            )
        suggestions = snapshot_sequence(
            items=self.suggestions, item_type=AlignmentSuggestion, field="Suggestions"
        )
        unmatched = snapshot_sequence(
            items=self.unmatched_proposal_ids, item_type=ProposalId, field="Unmatched occurrences"
        )
        gaps = snapshot_sequence(
            items=self.uncovered_reference_ids,
            item_type=ReferenceDefinitionId,
            field="Required reference gaps",
        )
        if (
            any(item.scope != self.scope for item in suggestions)
            or len({item.id for item in suggestions}) != len(suggestions)
            or len(set(unmatched)) != len(unmatched)
            or len(set(gaps)) != len(gaps)
        ):
            raise ValueError("Use distinct suggestions and gaps in this workspace")
        if self.reference_pack is None and (
            gaps or any(item.layer is AlignmentLayer.MODEL_TO_REFERENCE for item in suggestions)
        ):
            raise ValueError("Select an exact pack for reference suggestions or gaps")
        object.__setattr__(self, "suggestions", suggestions)
        object.__setattr__(self, "unmatched_proposal_ids", unmatched)
        object.__setattr__(self, "uncovered_reference_ids", gaps)

    def mark_prepared(self, *, expected_version: int) -> Alignment:
        """Advance once after the corresponding cases have been prepared."""
        require_exact(value=expected_version, expected=int, field="Expected alignment version")
        if self.version != expected_version or self.status is not AlignmentStatus.PROPOSED:
            raise StaleStateError(message="Inspect the current alignment before preparing cases.")
        return replace(self, status=AlignmentStatus.PREPARED, version=self.version + 1)
