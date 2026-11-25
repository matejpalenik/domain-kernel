"""Materialize the admitted v23 graph and share the structured provider contract."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Annotated, ClassVar
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.discovery.domain.models import Proposal
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.questions import Question
from domain_kernel.shared.domain.definitions import (
    ConceptDefinition,
    Definition,
    EvidenceBasis,
    RelationshipDefinition,
)
from domain_kernel.shared.domain.model_values import CardinalityBounds, RelationshipCardinality
from domain_kernel.shared.domain.naming import LOOKUP_NAME_PATTERN
from domain_kernel.shared.errors import InferenceError
from domain_kernel.shared.hashing import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic.config import JsonDict

    from domain_kernel.discovery.domain.models import DiscoveryDraft
    from domain_kernel.shared.application.inference import InferenceInput
    from domain_kernel.shared.domain.definitions import DefinitionBody
    from domain_kernel.sources.domain.models import Evidence


def _wire_schema(schema: JsonDict) -> None:
    # Editorial docstring changes must not invalidate provider receipts.
    _ = schema.pop("description", None)


class _Record(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", strict=True, json_schema_extra=_wire_schema
    )


type _Name = Annotated[str, Field(pattern=f"^{LOOKUP_NAME_PATTERN}$")]
type _Citation = Annotated[int, Field(gt=0)]
type _Text = Annotated[str, Field(min_length=1)]


class Concept(_Record):
    """A proposed reusable concept and the source passages supporting it."""

    name: _Name
    display_name: _Text
    meaning: _Text
    citations: Annotated[list[_Citation], Field(min_length=1)]


class Relationship(Concept):
    """A directed relationship between approved or proposed concepts."""

    source: _Name
    target: _Name


class Clarification(_Record):
    """An evidence-backed modeling question for expert review."""

    text: _Text
    citations: Annotated[list[_Citation], Field(min_length=1)]


class CandidateSchema(_Record):
    """The versioned schema candidates examined by the independent review stage."""

    concepts: list[Concept]
    relationships: list[Relationship]
    questions: list[Clarification]


def response_schema(model: type[_Record]) -> str:
    """Capture the independent modeling or admission request contract."""
    return canonical_json_bytes(value=model.model_json_schema()).decode()


def parse[T: _Record](*, model: type[T], payload: str) -> T:
    """Reject malformed provider output without exposing its contents."""
    try:
        return model.model_validate_json(payload)
    except ValidationError:
        raise InferenceError(message="Review the structured schema discovery response.") from None


def materialize(
    *,
    draft: DiscoveryDraft,
    candidate: CandidateSchema,
    inputs: Sequence[InferenceInput],
) -> DiscoveryDraft:
    """Materialize admitted meanings with exact citations and resolved type endpoints."""

    def identity(*, name: str, kind: str) -> str:
        return uuid5(NAMESPACE_URL, f"domain-kernel/{draft.run_id.value}/{kind}/{name}").hex

    def citations(*, indexes: Sequence[int]) -> tuple[Evidence, ...]:
        return tuple(
            dict.fromkeys(item for index in indexes for item in inputs[index - 1].evidence)
        )

    def proposal(*, row: Concept, body: DefinitionBody, indexes: Sequence[int]) -> Proposal:
        evidence = citations(indexes=indexes)
        return Proposal(
            id=ProposalId(value=identity(name=row.name, kind="proposal")),
            scope=draft.scope,
            definition=Definition(
                id=DefinitionId(value=identity(name=row.name, kind="definition")),
                revision=1,
                scope=draft.scope,
                name=row.name,
                display_name=row.display_name,
                meaning=row.meaning,
                body=body,
                basis=EvidenceBasis.HYPOTHESIS,
                evidence=evidence,
            ),
            basis=EvidenceBasis.HYPOTHESIS,
            evidence=evidence,
            provenance=draft.provenance,
        )

    endpoints = {
        item.name: item.id
        for item in draft.context.approved_definitions
        if isinstance(item.body, ConceptDefinition)
    }
    proposals: list[Proposal] = []
    for row in candidate.concepts:
        if row.name in endpoints:
            raise InferenceError(message="Reuse an approved concept through its exact endpoint.")
        item = proposal(row=row, body=ConceptDefinition(), indexes=row.citations)
        proposals.append(item)
        endpoints[row.name] = item.definition.id
    unbounded = CardinalityBounds(maximum=None)
    for row in candidate.relationships:
        if row.source not in endpoints or row.target not in endpoints:
            raise InferenceError(message="Admit both reusable endpoints before their relationship.")
        body = RelationshipDefinition(
            source_concept_id=endpoints[row.source],
            target_concept_id=endpoints[row.target],
            cardinality=RelationshipCardinality(outgoing=unbounded, incoming=unbounded),
        )
        proposals.append(proposal(row=row, body=body, indexes=row.citations))
    return replace(
        draft,
        schema_modeled=True,
        proposals=tuple(proposals),
        schema_questions=tuple(
            Question(
                id=QuestionId(value=identity(name=text, kind="question")),
                text=text,
                required=False,
                scope_text=draft.context.model_description,
                obligation_id=None,
                evidence=citations(indexes=indexes),
            )
            for text, indexes in _group_questions(questions=candidate.questions).items()
        ),
    )


def _group_questions(*, questions: Sequence[Clarification]) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = {}
    for item in questions:
        grouped.setdefault(item.text.strip(), []).extend(item.citations)
    return grouped
