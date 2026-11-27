"""A version-qualified source occurrence disposition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.shared.domain.enums.source_disposition import SourceDisposition
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence


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
