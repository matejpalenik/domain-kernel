"""Caller-provided purpose and applicability for schema discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import SourceRevision

type SourceRole = Literal["policy", "observed_practice", "template", "reference", "unknown"]


@dataclass(frozen=True, kw_only=True)
class CompetencyQuestion:
    """One business question the proposed model should help answer."""

    id: str
    text: str

    def __post_init__(self) -> None:
        """Require a stable identifier and a question."""
        TextValidation.require_text(value=self.id, field="Competency question ID")
        TextValidation.require_text(value=self.text, field="Competency question text")
        if self.id != self.id.strip():
            raise ValueError("Use a stable competency question ID without surrounding whitespace.")


@dataclass(frozen=True, kw_only=True)
class DiscoverySourceContext:
    """Caller-attested applicability of one ingested revision."""

    revision: SourceRevision
    role: SourceRole = "unknown"
    owner: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    supersedes: SourceRevision | None = None

    def __post_init__(self) -> None:
        """Check attributed identity and effective period."""
        RuntimeTypeValidation.require_exact(
            value=self.revision, expected=SourceRevision, field="Source revision"
        )
        if self.role not in ("policy", "observed_practice", "template", "reference", "unknown"):
            raise ValueError("Choose a supported role for the source revision.")
        if self.owner is not None:
            TextValidation.require_text(value=self.owner, field="Source owner")
        for value in (self.effective_from, self.effective_until):
            if value is not None:
                RuntimeTypeValidation.require_exact(
                    value=value, expected=date, field="Source effective date"
                )
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValueError("Use an ordered effective period.")
        if self.supersedes is not None:
            RuntimeTypeValidation.require_exact(
                value=self.supersedes, expected=SourceRevision, field="Superseded revision"
            )
            if (
                self.supersedes == self.revision
                or self.supersedes.project_id != self.revision.project_id
            ):
                raise ValueError("Use a different superseded revision in this project.")


@dataclass(frozen=True, kw_only=True)
class SchemaDiscoveryOptions:
    """Pin the business purpose and source context used by schema discovery."""

    competency_questions: tuple[CompetencyQuestion, ...] = ()
    source_context: tuple[DiscoverySourceContext, ...] = ()
    as_of: date | None = None

    def __post_init__(self) -> None:
        """Capture one purpose and context per revision."""
        questions = SequenceValidation.snapshot_sequence(
            items=self.competency_questions,
            item_type=CompetencyQuestion,
            field="Competency questions",
        )
        contexts = SequenceValidation.snapshot_sequence(
            items=self.source_context, item_type=DiscoverySourceContext, field="Source contexts"
        )
        if len({question.id for question in questions}) != len(questions):
            raise ValueError("Supply distinct competency question IDs.")
        if len({context.revision for context in contexts}) != len(contexts):
            raise ValueError("Supply one context per exact source revision.")
        if self.as_of is not None:
            RuntimeTypeValidation.require_exact(
                value=self.as_of, expected=date, field="Discovery as-of date"
            )
        object.__setattr__(self, "competency_questions", questions)
        object.__setattr__(self, "source_context", contexts)
