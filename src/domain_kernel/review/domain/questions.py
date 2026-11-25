"""Read-only questions and exact applicability of review requirements."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING

from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence


@unique
class RequirementKind(StrEnum):
    """The source of an explicit review requirement."""

    CORE = "core"
    EVIDENCE = "evidence"
    REFERENCE_PACK = "reference_pack"


@unique
class QuestionDisposition(StrEnum):
    """The durable resolution of one inspected open question."""

    UNRESOLVED = "unresolved"
    ANSWERED = "answered"
    REVIEWED_NONBLOCKING = "reviewed_nonblocking"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, kw_only=True)
class ReviewRequirement:
    """An explicit requirement, optionally bound to an exact reference obligation."""

    kind: RequirementKind
    code: str
    required: bool
    reference_pack: ReferencePackPin | None = None
    obligation_id: ObligationId | None = None

    def __post_init__(self) -> None:
        """Validate the exact authority of the requirement."""
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=RequirementKind, field="Requirement kind"
        )
        RuntimeTypeValidation.require_exact(
            value=self.required, expected=bool, field="Requiredness"
        )
        TextValidation.require_text(value=self.code, field="Requirement code")
        if self.kind is RequirementKind.REFERENCE_PACK:
            RuntimeTypeValidation.require_exact(
                value=self.reference_pack, expected=ReferencePackPin, field="Reference pack"
            )
            RuntimeTypeValidation.require_exact(
                value=self.obligation_id, expected=ObligationId, field="Obligation ID"
            )
        elif self.reference_pack is not None or self.obligation_id is not None:
            raise ValueError("Associate an exact pack only with a reference-pack requirement")

    def applies_to(self, *, pack: ReferencePackPin | None) -> bool:
        """Check whether this requirement governs the current reviewed context."""
        return self.kind is not RequirementKind.REFERENCE_PACK or self.reference_pack == pack


@dataclass(frozen=True, kw_only=True)
class Question:
    """An inspected question and its attributed resolution."""

    id: QuestionId
    text: str
    required: bool
    scope_text: str
    obligation_id: ObligationId | None
    evidence: Sequence[Evidence]
    disposition: QuestionDisposition = QuestionDisposition.UNRESOLVED
    rationale: str | None = None
    reviewer: str | None = None
    decision_id: DecisionId | None = None

    def __post_init__(self) -> None:
        """Retain the exact question scope, citations and disposition."""
        RuntimeTypeValidation.require_exact(value=self.id, expected=QuestionId, field="Question ID")
        TextValidation.require_text(value=self.text, field="Question")
        RuntimeTypeValidation.require_exact(
            value=self.required, expected=bool, field="Question requiredness"
        )
        TextValidation.require_text(value=self.scope_text, field="Question scope")
        RuntimeTypeValidation.require_exact(
            value=self.disposition, expected=QuestionDisposition, field="Question disposition"
        )
        if self.obligation_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.obligation_id, expected=ObligationId, field="Question obligation"
            )
        if self.decision_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.decision_id, expected=DecisionId, field="Question decision"
            )
        for value in (self.rationale, self.reviewer):
            if value is not None:
                TextValidation.require_text(value=value, field="Question review attribution")
        if self.disposition is QuestionDisposition.REVIEWED_NONBLOCKING and (
            self.required
            or self.rationale is None
            or self.reviewer is None
            or self.decision_id is None
        ):
            raise ValueError("Record an attributed nonblocking decision for an optional question")
        object.__setattr__(
            self,
            "evidence",
            SequenceValidation.snapshot_sequence(
                items=self.evidence, item_type=Evidence, field="Question evidence"
            ),
        )
