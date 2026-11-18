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
from domain_kernel.shared.contracts import Issue
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


def output_error(*, code: str, path: tuple[str | int, ...], message: str) -> InferenceError:
    """Identify a field without echoing untrusted provider content."""
    location = ".".join(map(str, path)) or "response"
    detail = f"Review provider output at {location}. {message}"
    return InferenceError(message=detail, issue=Issue(code=code, path=path, message=detail))


def _shape_error(*, error: ValidationError) -> InferenceError:
    item = error.errors(include_input=False, include_context=False, include_url=False)[0]
    fields = {*_Response.model_fields, *_RelationFields.model_fields}
    path = tuple(i if isinstance(i, int) or i in fields else "<field>" for i in item["loc"])
    return output_error(code="invalid_shape", path=path, message=f"Schema check: {item['type']}.")


def _proposal(
    *,
    row: _DraftFields,
    body: DefinitionBody,
    scope: ModelScope,
    corpus: Sequence[Evidence],
    provenance: ExtractionProvenance,
) -> Proposal:
    evidence = tuple(corpus[index - 1] for index in row.citations)
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


def _check_fields(*, result: _Response, limit: int, citations: int, available: set[str]) -> None:
    if len(result.concepts) + len(result.relationships) > limit:
        raise output_error(code="proposal_limit", path=(), message="Reduce the batch size.")
    seen: set[str] = set()
    for group, rows in (("concepts", result.concepts), ("relationships", result.relationships)):
        for index, row in enumerate(rows):
            path = (group, index)
            if row.name in seen:
                raise output_error(
                    code="duplicate_name",
                    path=(*path, "name"),
                    message="Use a unique proposal name.",
                )
            seen.add(row.name)
            _check_row(row=row, path=path, citations=citations, available=available)


def _check_row(
    *, row: _DraftFields, path: tuple[str, int], citations: int, available: set[str]
) -> None:
    for field, value in (("meaning", row.meaning), ("display_name", row.display_name)):
        if not value.strip():
            raise output_error(
                code="empty_text", path=(*path, field), message="Supply nonblank text."
            )
    for pos, citation in enumerate(row.citations):
        if citation > citations or citation in row.citations[:pos]:
            raise output_error(
                code="invalid_citation",
                path=(*path, "citations", pos),
                message="Use a distinct index from the supplied passages.",
            )
    _check_confidence(value=row.confidence, path=path)
    if isinstance(row, _RelationFields):
        for field, endpoint in (("source", row.source), ("target", row.target)):
            if endpoint not in available:
                raise output_error(
                    code="unknown_endpoint",
                    path=(*path, field),
                    message="Use the name of an approved or proposed concept.",
                )


def _check_confidence(*, value: str | None, path: tuple[str, int]) -> None:
    if value is not None:
        try:
            confidence = Decimal(value)
        except InvalidOperation:
            confidence = Decimal("NaN")
        if not confidence.is_finite() or not 0 <= confidence <= 1:
            raise output_error(
                code="invalid_confidence",
                path=(*path, "confidence"),
                message="Supply null or a decimal between zero and one.",
            )


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
    except ValidationError as error:
        raise _shape_error(error=error) from None
    _check_fields(
        result=result,
        limit=max_proposals,
        citations=len(corpus),
        available={
            item.name
            for item in context.approved_definitions
            if item.kind is DefinitionKind.CONCEPT
        }
        | {item.name for item in result.concepts},
    )
    try:
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
