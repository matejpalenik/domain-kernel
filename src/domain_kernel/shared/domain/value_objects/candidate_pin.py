from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class CandidatePin:
    """Reference to an exact compiled model snapshot."""

    scope: ModelScope
    candidate_id: CandidateId
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Keep candidate, scope and content hash nominally distinct."""
        RuntimeTypeValidation.require_exact(
            value=self.scope, expected=ModelScope, field="Candidate scope"
        )
        RuntimeTypeValidation.require_exact(
            value=self.candidate_id, expected=CandidateId, field="Candidate identity"
        )
        RuntimeTypeValidation.require_exact(
            value=self.content_hash, expected=ContentHash, field="Candidate hash"
        )
