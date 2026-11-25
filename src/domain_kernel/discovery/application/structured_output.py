"""The closed structured discovery response and its conversion to typed drafts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Annotated, ClassVar
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain_kernel._shared.domain.definitions import (
    ConceptDefinition,
    Definition,
    EvidenceBasis,
    RelationshipDefinition,
)
from domain_kernel._shared.domain.model_values import CardinalityBounds, RelationshipCardinality
from domain_kernel._shared.domain.naming import LOOKUP_NAME_PATTERN
from domain_kernel.discovery.application.claim_extraction import Anchor, normalized
from domain_kernel.discovery.application.endpoint_contract import (
    REPAIR_VERSION,
    BindingEnvelope,
    EndpointReference,
    approved_key,
)
from domain_kernel.discovery.application.held_endpoints import HeldClaim, HeldClaims
from domain_kernel.discovery.domain.bindings import (
    BindingWitness,
    EndpointBinding,
    HeldRelationship,
    RelationshipBinding,
)
from domain_kernel.discovery.domain.models import Proposal
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import InferenceError
from domain_kernel.shared.hashing import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.application.inference import InferenceInput
    from domain_kernel._shared.domain.definitions import DefinitionBody
    from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
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


def _proposal(  # noqa: PLR0913 - Construct one proposal and its captured identity.
    *,
    row: _DraftFields,
    body: DefinitionBody,
    scope: ModelScope,
    corpus: Sequence[Evidence],
    provenance: ExtractionProvenance,
    identifier: DefinitionId | None = None,
) -> Proposal:
    evidence = tuple(corpus[index - 1] for index in row.citations)
    basis = EvidenceBasis.HYPOTHESIS
    return Proposal(
        id=ProposalId(value=uuid4().hex),
        scope=scope,
        definition=Definition(
            id=identifier or DefinitionId(value=uuid4().hex),
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


def _check_fields(
    *, result: _Response, limit: int | None, citations: int, available: set[str]
) -> None:
    if limit is not None and len(result.concepts) + len(result.relationships) > limit:
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
    max_proposals: int | None,
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


def decode_held_relationships(
    *, content: str, inputs: Sequence[InferenceInput], proposals: Sequence[Proposal]
) -> tuple[tuple[HeldRelationship, ...], dict[DefinitionId, HeldRelationship]]:
    """Resolve held evidence and link provisional holds to their typed relationship IDs."""
    by_name = {
        p.definition.name: p.definition.id
        for p in proposals
        if isinstance(p.definition.body, RelationshipDefinition)
    }
    held: list[HeldRelationship] = []
    provisional: dict[DefinitionId, HeldRelationship] = {}
    try:
        for item in HeldClaims.model_validate_json(content).held:
            claim = _held_relationship(item=item, inputs=inputs)
            if item.proposal_name is None:
                held.append(claim)
                continue
            identifier = by_name[item.proposal_name]
            if identifier in provisional:
                raise InferenceError(message="Use one conditional hold per relationship proposal.")
            provisional[identifier] = claim
    except (ValidationError, TypeError, ValueError, KeyError):
        raise InferenceError(message="Use exact source evidence for held relationships.") from None
    return tuple(held), provisional


def _held_relationship(*, item: HeldClaim, inputs: Sequence[InferenceInput]) -> HeldRelationship:
    claim = item.claim
    if claim.kind != "relationship" or not claim.source or not claim.target:
        raise ValueError("Hold an ordered relationship claim.")
    witnesses: list[BindingWitness] = []
    for qualifier in (claim, *claim.conditions, *claim.exceptions):
        for anchor in qualifier.evidence:
            passage = _quoted_input(inputs=inputs, anchor=anchor)
            witnesses.append(BindingWitness(evidence=passage.evidence[0], quote=anchor.quote))
    return HeldRelationship(
        claim_id=claim.claim_id,
        predicate=claim.name,
        source=claim.source,
        target=claim.target,
        meaning=claim.meaning,
        reason=item.reason,
        evidence=tuple(dict.fromkeys(witnesses)),
        conditions=tuple(q.text for q in claim.conditions),
        exceptions=tuple(q.text for q in claim.exceptions),
        dependency_ids=tuple(DefinitionId(value=identity) for identity in item.dependency_ids),
    )


def _quoted_input(*, inputs: Sequence[InferenceInput], anchor: Anchor) -> InferenceInput:
    if not 1 <= anchor.citation <= len(inputs):
        raise ValueError("Use an issued citation.")
    passage = inputs[anchor.citation - 1]
    if not normalized(anchor.quote) or normalized(anchor.quote) not in normalized(passage.text):
        raise ValueError("Use a quotation from the exact passage.")
    return passage


@dataclass(frozen=True, kw_only=True)
class BoundProposalInput:
    """The admitted source passages and pinned workspace for a versioned handoff."""

    context: InterpretationContext
    inputs: Sequence[InferenceInput]
    provenance: ExtractionProvenance
    run_id: DiscoveryRunId
    max_proposals: int

    def identity(self, *, key: str, kind: str) -> DefinitionId:
        """Allocate the same proposed definition identity on an exact run replay."""
        scope = self.context.scope
        name = canonical_json_bytes(
            value=(
                "discovery-definition-v2",
                scope.project_id.value,
                scope.model_id.value,
                self.run_id.value,
                kind,
                key,
            )
        ).decode()
        return DefinitionId(value=uuid5(NAMESPACE_URL, name).hex)

    def evidence(self, *, anchor: Anchor) -> Evidence:
        """Check the handoff quotation against the original request inventory."""
        return _quoted_input(inputs=self.inputs, anchor=anchor).evidence[0]

    def endpoint(
        self, *, reference: EndpointReference | None, concepts: dict[str, Definition]
    ) -> EndpointBinding | None:
        """Bind only the span and internal concept key carried by the staged adapter."""
        if reference is None:
            return None
        mention = reference.occurrence
        anchor = self.evidence(anchor=mention.anchor)
        text = self.inputs[mention.anchor.citation - 1].text
        if not (0 <= mention.start < mention.end <= len(text)) or (
            text[mention.start : mention.end] != mention.anchor.quote
        ):
            raise ValueError("Use the exact character span of the participant.")
        concept = concepts.get(reference.concept_key or "")
        return EndpointBinding(
            mention_id=mention.id,
            evidence=anchor,
            start=mention.start,
            end=mention.end,
            quote=mention.anchor.quote,
            definition_id=concept.id if concept else None,
            definition_revision=concept.revision if concept else None,
        )

    def witnesses(self, *, anchors: Sequence[Anchor]) -> tuple[BindingWitness, ...]:
        """Retain both the exact issued citation and the verified wording."""
        return tuple(
            dict.fromkeys(
                BindingWitness(evidence=self.evidence(anchor=anchor), quote=anchor.quote)
                for anchor in anchors
            )
        )


def decode_bound_proposals(
    *, output: str, binding_json: str, request: BoundProposalInput
) -> tuple[tuple[Proposal, ...], tuple[RelationshipBinding, ...]]:
    """Validate the staged adapter's handoff without resolving edges through display names."""
    try:
        result = _Response.model_validate_json(output)
        envelope = BindingEnvelope.model_validate_json(binding_json)
        approved = {
            item.name: item
            for item in request.context.approved_definitions
            if item.kind is DefinitionKind.CONCEPT
        }
        corpus = tuple(item.evidence[0] for item in request.inputs)
        names = {item.name for item in result.concepts}
        _check_fields(
            result=result,
            limit=request.max_proposals,
            citations=len(corpus),
            available=names | approved.keys(),
        )
        _check_concept_projection(names=names, envelope=envelope, approved=set(approved))
        concepts = {
            approved_key(identity=item.id.value, revision=item.revision): item
            for item in approved.values()
        }
        rows = {item.name: item for item in result.concepts}
        proposals: list[Proposal] = []
        for key, name in envelope.concepts.items():
            proposal = _proposal(
                row=rows[name],
                body=ConceptDefinition(),
                scope=request.context.scope,
                corpus=corpus,
                provenance=request.provenance,
                identifier=request.identity(key=key, kind="concept"),
            )
            concepts[key] = proposal.definition
            proposals.append(proposal)
        edges = _bound_relationships(
            result=result,
            envelope=envelope,
            request=request,
            concepts=concepts,
            corpus=corpus,
        )
    except (ValidationError, TypeError, ValueError, KeyError, InvalidOperation):
        raise output_error(
            code="invalid_endpoint_binding",
            path=("relationships",),
            message="Use exact issued endpoint bindings and source evidence.",
        ) from None
    return (*proposals, *edges[0]), edges[1]


def _check_concept_projection(
    *, names: set[str], envelope: BindingEnvelope, approved: set[str]
) -> None:
    if (
        len(names) != len(envelope.concepts)
        or names != set(envelope.concepts.values())
        or names.intersection(approved)
        or any(
            not key.startswith("entity-" if envelope.contract == REPAIR_VERSION else "m-")
            for key in envelope.concepts
        )
    ):
        raise ValueError("Bind each staged concept to one proposal.")


def _bound_relationships(
    *,
    result: _Response,
    envelope: BindingEnvelope,
    request: BoundProposalInput,
    concepts: dict[str, Definition],
    corpus: Sequence[Evidence],
) -> tuple[tuple[Proposal, ...], tuple[RelationshipBinding, ...]]:
    proposals: list[Proposal] = []
    bindings: list[RelationshipBinding] = []
    rows = {item.name: item for item in result.relationships}
    cardinality = RelationshipCardinality(
        outgoing=CardinalityBounds(maximum=None), incoming=CardinalityBounds(maximum=None)
    )
    for edge in envelope.edges:
        source = request.endpoint(reference=edge.source, concepts=concepts)
        target = request.endpoint(reference=edge.target, concepts=concepts)
        identifier = None
        if edge.proposal_name is not None:
            row = rows.pop(edge.proposal_name)
            if (
                source is None
                or target is None
                or source.definition_id is None
                or target.definition_id is None
            ):
                raise ValueError("Resolve both endpoints before proposing an edge.")
            identifier = request.identity(key=edge.claim_id, kind="relationship")
            proposals.append(
                _proposal(
                    row=row,
                    scope=request.context.scope,
                    corpus=corpus,
                    provenance=request.provenance,
                    identifier=identifier,
                    body=RelationshipDefinition(
                        source_concept_id=source.definition_id,
                        target_concept_id=target.definition_id,
                        cardinality=cardinality,
                    ),
                )
            )
        bindings.append(
            RelationshipBinding(
                claim_id=edge.claim_id,
                relationship_id=identifier,
                source=source,
                target=target,
                evidence=request.witnesses(anchors=edge.evidence),
                identity_evidence=request.witnesses(anchors=edge.identity_evidence),
                origin_claim_ids=tuple(edge.origin_claim_ids),
                reason=edge.reason,
                previous_source=request.endpoint(reference=edge.previous_source, concepts=concepts),
                previous_target=request.endpoint(reference=edge.previous_target, concepts=concepts),
            )
        )
    if rows:
        raise ValueError("Bind every staged relationship.")
    return tuple(proposals), tuple(bindings)
