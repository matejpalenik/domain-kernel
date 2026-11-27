"""A definition's disposition with its original reviewed rationale."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.reference_packs.domain.contracts import ReferenceAlignment
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.shared.domain.enums.reference_disposition_kind import ReferenceDispositionKind
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation


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
