"""Conservative occurrence proof and routing for Decisions endpoint checks."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, ValidationError

from domain_kernel.discovery.application import evidence_binding, held_endpoints, scope_shadow
from domain_kernel.discovery.application.claim_extraction import BoundClaim, normalized
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.json_value import JsonValue  # noqa: TC001 - Pydantic resolves Reply.

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.discovery.application.claim_extraction import BatchResult, IdentifiedClaim
    from domain_kernel.discovery.application.claim_graph import ClaimGraph
    from domain_kernel.discovery.application.contracts.inference_input import InferenceInput


VERSION = "endpoint-decisions-exact-occurrences-v1"
TEMPLATE = "id-full-claim-v1"
MODEL = "gpt-6-luna"
THRESHOLD = 0.90
LABELS = ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE")
_ROUNDING = 0.015001
_MAX_SENTENCE_BYTES = 512
_SCOPE_WORDS = [
    "no",
    "not",
    "never",
    "unless",
    "except",
    "if",
    "when",
    "only",
    "may",
    "might",
    "could",
    "should",
    "must",
    "would",
    "can",
    "shall",
    "will",
    "and",
    "or",
    "both",
    "all",
    "every",
    "some",
    "during",
    "before",
    "after",
    "although",
    "despite",
]
_QUALIFIED = re.compile(rf"\b(?:{'|'.join(_SCOPE_WORDS)})\b", re.IGNORECASE)
_ARTICLE = r"(?:(?:the|a|an)\s+)?"
_VERB = r"(?P<verb>[^\W\d_]+)"
_NON_ACTION = frozenset(
    {"is", "are", "was", "were", "be", "been", "of", "in", "with", "to", "for", "from", "by", "as"}
)
_INSTRUCTIONS = (
    "Using only the passages listed in the evidence for claim {claim_id}, classify whether "
    "they establish the exact subject\u2013predicate\u2013object relationship in the stated "
    "direction, including all qualifiers. Choose SUPPORTED, CONTRADICTED, or "
    "INSUFFICIENT_EVIDENCE. Evaluate this exact claim. {statement}"
)


class Route(BaseModel):
    """Reopenable gate outcome for one relationship in the assembled graph."""

    claim_id: str
    evidence_ids: tuple[str, ...]
    reason: str
    support: float | None = None
    citation: int | None = None
    quote_digest: str | None = None
    endpoint_claim_ids: tuple[str, str] | None = None
    endpoint_spans: tuple[tuple[int, int], tuple[int, int]] | None = None


class CallReceipt(BaseModel):
    """Detached usage and timing for one replayable Decisions packet."""

    request_digest: str
    claim_ids: tuple[str, ...]
    status: str
    seconds: float | None = None
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class Audit(BaseModel):
    """Gate policy and individual routes pinned with the checked graph."""

    version: str = VERSION
    template: str = TEMPLATE
    threshold: float = THRESHOLD
    model: str = MODEL
    routes: list[Route]
    calls: list[CallReceipt] = Field(default_factory=list)


@dataclass(frozen=True, kw_only=True, slots=True)
class Candidate:
    """One assertion and both matched endpoint occurrences within its pinned passage."""

    claim: IdentifiedClaim
    source: IdentifiedClaim
    target: IdentifiedClaim
    passage: InferenceInput
    quote: str
    spans: tuple[tuple[int, int], tuple[int, int]]


def _bare(text: str) -> str:
    return normalized(text).rstrip(".").casefold()


def _mention(name: str) -> str:
    return r"\s+".join(map(re.escape, name.split("-")))


def _simple_roles(*, claim: IdentifiedClaim, quote: str) -> re.Match[str] | None:
    if claim.source is None or claim.target is None or claim.source == claim.target:
        return None
    source, target = _mention(claim.source), _mention(claim.target)
    match = re.fullmatch(
        rf"{_ARTICLE}(?P<actor>{source})\s+{_VERB}\s+{_ARTICLE}(?P<object>{target})\.?",
        quote,
        flags=re.IGNORECASE,
    )
    if match is None or match["verb"].casefold() in _NON_ACTION:
        return None
    if _bare(claim.title) not in {match["verb"].casefold(), _bare(quote)}:
        return None
    if any(
        len(re.findall(rf"(?<!\w){term}(?!\w)", quote, re.IGNORECASE)) != 1
        for term in (source, target)
    ):
        return None
    return match


def _definition_witness(
    *, concept: IdentifiedClaim, citation: int, span: tuple[int, int], text: str, quote: str
) -> bool:
    # A richer or separately scoped definition requires interpretation by the endpoint verifier.
    if concept.conditions or concept.exceptions or _QUALIFIED.search(concept.meaning):
        return False
    label = rf"{_ARTICLE}{_mention(concept.name)}"
    if re.fullmatch(label, _bare(concept.title)) is None:
        return False
    if (
        _bare(concept.meaning) != _bare(quote)
        and re.fullmatch(label, _bare(concept.meaning)) is None
    ):
        return False
    for anchor in concept.evidence:
        if anchor.citation != citation:
            continue
        exact = evidence_binding.exact_quote(text=text, quote=anchor.quote)
        if exact is not None and (start := text.find(exact)) <= span[0] < span[1] <= start + len(
            exact
        ):
            return True
    return False


def _candidate(
    *,
    claim: IdentifiedClaim,
    inputs: Sequence[InferenceInput],
    concepts: dict[str, IdentifiedClaim],
) -> Candidate | None:
    if len(claim.evidence) != 1 or not claim.source or not claim.target:
        return None
    source, target = concepts.get(claim.source), concepts.get(claim.target)
    anchor = claim.evidence[0]
    if source is None or target is None or not 1 <= anchor.citation <= len(inputs):
        return None
    part = inputs[anchor.citation - 1]
    exact = (
        None
        if part.is_table
        else held_endpoints.containing_span(text=part.text, quote=anchor.quote, row=False)
    )
    if (
        exact is None
        or len(exact.encode()) > _MAX_SENTENCE_BYTES
        or _QUALIFIED.search(exact)
        or _bare(claim.meaning) != _bare(exact)
    ):
        return None
    match = _simple_roles(claim=claim, quote=exact)
    if match is None:
        return None
    start = part.text.index(exact)
    left = (start + match.start("actor"), start + match.end("actor"))
    right = (start + match.start("object"), start + match.end("object"))
    if not all(
        _definition_witness(
            concept=concept, citation=anchor.citation, span=span, text=part.text, quote=exact
        )
        for concept, span in ((source, left), (target, right))
    ):
        return None
    return Candidate(
        claim=claim, source=source, target=target, quote=exact, passage=part, spans=(left, right)
    )


def plan(
    *,
    graph: ClaimGraph,
    batches: Sequence[BatchResult],
    inputs: Sequence[InferenceInput],
    blocked_names: set[str],
) -> tuple[Audit, list[Candidate]]:
    """Select only unchanged aggregate claims with independently pinned endpoint definitions."""
    accepted = {row.claim_id: row for batch in batches for row in batch.accepted}
    repaired = {a.claim_id for batch in batches for a in batch.assessments if a.stage == "repair"}
    named = Counter(row.name for row in graph.claims if row.kind == "concept")
    concepts = {
        row.name: row
        for row in graph.claims
        if row.kind == "concept"
        and named[row.name] == 1
        and row.claim_id not in repaired
        and len(graph.origins[row.claim_id]) == 1
        and not isinstance(row, BoundClaim)
    }
    routes: list[Route] = []
    candidates: list[Candidate] = []
    for row in graph.claims:
        if row.kind != "relationship":
            continue
        candidate = None
        if (
            row.claim_id in repaired
            or len(graph.origins[row.claim_id]) != 1
            or row != accepted[row.claim_id]
        ):
            reason = "changed_or_repaired"
        elif (
            isinstance(row, BoundClaim)
            or row.conditions
            or row.exceptions
            or _QUALIFIED.search(row.meaning)
        ):
            reason = "qualified_or_specialized"
        elif row.source in blocked_names or row.target in blocked_names:
            reason = "alias_or_external_endpoint"
        elif scope_shadow.inspect(rows=[row], inputs=inputs).findings:
            reason = "scope_finding"
        else:
            candidate = _candidate(claim=row, inputs=inputs, concepts=concepts)
            reason = "endpoint_proof_required" if candidate is None else "eligible"
        routes.append(_route(claim=row, inputs=inputs, reason=reason, candidate=candidate))
        if candidate is not None:
            candidates.append(candidate)
    return Audit(routes=routes), candidates


def _route(
    *,
    claim: IdentifiedClaim,
    inputs: Sequence[InferenceInput],
    reason: str,
    candidate: Candidate | None,
) -> Route:
    ids = tuple(
        dict.fromkeys(
            item.id.value
            for anchor in claim.evidence
            if 1 <= anchor.citation <= len(inputs)
            for item in inputs[anchor.citation - 1].evidence
        )
    )
    return Route(
        claim_id=claim.claim_id,
        evidence_ids=ids,
        reason=reason,
        citation=None if candidate is None else candidate.claim.evidence[0].citation,
        quote_digest=None
        if candidate is None
        else Hashing.hash_bytes(content=candidate.quote.encode()).value,
        endpoint_claim_ids=None
        if candidate is None
        else (candidate.source.claim_id, candidate.target.claim_id),
        endpoint_spans=None if candidate is None else candidate.spans,
    )


def body(candidates: Sequence[Candidate], /) -> dict[str, JsonValue]:
    """Build the tested per-ID choice template over deduplicated source quotes."""
    quotes: dict[str, str] = {}
    passages: dict[str, JsonValue] = {}
    claims: dict[str, JsonValue] = {}
    questions: list[JsonValue] = []
    for candidate in candidates:
        row = candidate.claim
        reference = quotes.setdefault(candidate.quote, f"p{len(quotes) + 1}")
        passages[reference] = candidate.quote
        claims[row.claim_id] = {
            "subject": row.source,
            "predicate": row.title,
            "object": row.target,
            "qualifiers": [],
            "evidence": [reference],
        }
        questions.append(
            {
                "type": "choice",
                "name": row.claim_id,
                "instructions": _INSTRUCTIONS.format(claim_id=row.claim_id, statement=row.meaning),
                "choices": [{"value": label} for label in LABELS],
            }
        )
    return {
        "model": MODEL,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_json", "data": {"passages": passages, "claims": claims}}
                ],
            }
        ],
        "questions": questions,
    }


type _Label = Literal["SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE"]


class _Probability(BaseModel, strict=True):
    value: _Label
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)


class _Choice(BaseModel, strict=True):
    type: Literal["choice"]
    name: str
    choice: _Label
    probabilities: list[_Probability]


class Reply(BaseModel, strict=True):
    """Retained detached answer array, with validation isolated to each question."""

    answers: list[JsonValue] = Field(default_factory=list)
    status: Literal["ok", "malformed", "unavailable", "timeout"]
    seconds: float = Field(ge=0, allow_inf_nan=False)


def outcomes(*, reply: Reply, ids: Sequence[str]) -> dict[str, tuple[str, float | None]]:
    """Never infer support from a missing, malformed or non-supporting answer."""
    if reply.status != "ok":
        return dict.fromkeys(ids, (reply.status, None))
    indexed: dict[str, list[JsonValue]] = defaultdict(list)
    for answer in reply.answers:
        if isinstance(answer, dict) and isinstance(name := answer.get("name"), str):
            indexed[name].append(answer)
    return {claim_id: _outcome(indexed[claim_id]) for claim_id in ids}


def _outcome(answers: list[JsonValue], /) -> tuple[str, float | None]:
    if len(answers) != 1:
        return ("ambiguous_answer" if answers else "missing_answer"), None
    answer = answers[0]
    if isinstance(answer, dict) and answer.get("type") == "refusal":
        return "refused", None
    try:
        choice = _Choice.model_validate(answer)
    except ValidationError:
        return "malformed_answer", None
    distribution = {p.value: p.probability for p in choice.probabilities}
    if (
        Counter(p.value for p in choice.probabilities) != Counter(LABELS)
        or abs(sum(distribution.values()) - 1) > _ROUNDING
    ):
        return "malformed_answer", None
    score = distribution["SUPPORTED"]
    if choice.choice != "SUPPORTED":
        return "non_supporting_choice", score
    return ("supported" if score >= THRESHOLD else "below_threshold"), score
