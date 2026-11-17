"""The closed structured discovery response and its conversion to typed drafts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Annotated, ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain_kernel._shared.domain.definitions import (
    ConceptDefinition,
    Definition,
    EvidenceBasis,
    RelationshipDefinition,
)
from domain_kernel._shared.domain.model_values import CardinalityBounds, RelationshipCardinality
from domain_kernel._shared.domain.naming import LOOKUP_NAME_PATTERN
from domain_kernel.discovery.domain.models import Proposal
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.shared.errors import InferenceError
from domain_kernel.shared.hashing import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.definitions import DefinitionBody
    from domain_kernel.discovery.domain.models import ExtractionProvenance, InterpretationContext
    from domain_kernel.shared.contracts import ModelScope
    from domain_kernel.sources.domain.models import Evidence


type _LookupName = Annotated[str, Field(pattern=f"^{LOOKUP_NAME_PATTERN}$")]
type _CitationIndex = Annotated[int, Field(gt=0)]


class _DraftFields(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", strict=True, hide_input_in_errors=True
    )

    name: _LookupName
    display_name: Annotated[str, Field(min_length=1)]
    meaning: Annotated[str, Field(min_length=1)]
    citations: Annotated[list[_CitationIndex], Field(min_length=1)]
    confidence: str | None


class _RelationFields(_DraftFields):
    source: _LookupName
    target: _LookupName


class _Response(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", strict=True, hide_input_in_errors=True
    )

    concepts: list[_DraftFields]
    relationships: list[_RelationFields]


def response_schema() -> str:
    """Encode the fixed object and response field contract."""
    return canonical_json_bytes(value=_Response.model_json_schema()).decode()


def _evidence(*, indexes: list[int], corpus: Sequence[Evidence]) -> tuple[Evidence, ...]:
    if (
        not indexes
        or len(indexes) != len(set(indexes))
        or any(not 1 <= index <= len(corpus) for index in indexes)
    ):
        raise ValueError("Cite distinct one-based indexes from the supplied corpus")
    return tuple(corpus[index - 1] for index in indexes)


def _proposal(
    *,
    row: _DraftFields,
    body: DefinitionBody,
    scope: ModelScope,
    corpus: Sequence[Evidence],
    provenance: ExtractionProvenance,
) -> Proposal:
    evidence = _evidence(indexes=row.citations, corpus=corpus)
    basis = EvidenceBasis.HYPOTHESIS
    return Proposal(
        id=ProposalId(value=uuid4().hex),
        scope=scope,
        definition=Definition(
            id=DefinitionId(value=uuid4().hex),
            revision=1,
            scope=scope,
            name=row.name,
            display_name=row.display_name,
            meaning=row.meaning,
            body=body,
            basis=basis,
            evidence=evidence,
        ),
        basis=basis,
        evidence=evidence,
        confidence=None if row.confidence is None else Decimal(row.confidence),
        provenance=provenance,
    )


def _check_proposal_names(*, result: _Response, limit: int) -> None:
    rows = (*result.concepts, *result.relationships)
    if len(rows) > limit or len({row.name for row in rows}) != len(rows):
        raise ValueError("Use distinct lookup names within the proposal limit")


def decode_proposals(
    *,
    output: str,
    context: InterpretationContext,
    corpus: Sequence[Evidence],
    provenance: ExtractionProvenance,
    max_proposals: int,
) -> tuple[Proposal, ...]:
    """Validate the entire provider response before exposing any typed proposal."""
    try:
        result = _Response.model_validate_json(output)
        _check_proposal_names(result=result, limit=max_proposals)
        proposals = [
            _proposal(
                row=row,
                body=ConceptDefinition(),
                scope=context.scope,
                corpus=corpus,
                provenance=provenance,
            )
            for row in result.concepts
        ]
        available = {
            item.name: item.id
            for item in context.approved_definitions
            if item.kind is DefinitionKind.CONCEPT
        }
        available.update({item.definition.name: item.definition.id for item in proposals})
        cardinality = RelationshipCardinality(
            outgoing=CardinalityBounds(maximum=None),
            incoming=CardinalityBounds(maximum=None),
        )
        for relation in result.relationships:
            body = RelationshipDefinition(
                source_concept_id=available[relation.source],
                target_concept_id=available[relation.target],
                cardinality=cardinality,
            )
            proposals.append(
                _proposal(
                    row=relation,
                    body=body,
                    scope=context.scope,
                    corpus=corpus,
                    provenance=provenance,
                )
            )
    except (ValidationError, TypeError, ValueError, KeyError, InvalidOperation):
        raise InferenceError(
            message="Review provider output for complete typed proposals and exact citations.",
        ) from None
    return tuple(proposals)
