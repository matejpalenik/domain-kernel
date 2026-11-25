"""Optional staged document discovery. Approved model state belongs to the SDK."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from functools import partial
from importlib import import_module
from itertools import batched, chain, combinations
from math import inf
from time import monotonic
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict, final, override, runtime_checkable

from pydantic import BaseModel, TypeAdapter, ValidationError

from domain_kernel.discovery.application import (
    aggregate_verification,
    continuation_bindings,
    endpoint_contract,
    endpoint_decisions,
    endpoint_repair,
    evidence_binding,
    focused_omissions,
    held_endpoints,
    omission_windows,
    schema_evidence,
    scope_shadow,
)
from domain_kernel.discovery.application.claim_extraction import (
    ALIGNED_ENDPOINTS,
    CHECK_EDGES,
    COLLAPSED_ENDPOINTS,
    CONFIRM_SELF_ACTION,
    EXTRACT,
    INITIAL_EXTRACTION,
    OMISSIONS,
    RECONCILE,
    REPAIR,
    VERIFY,
    VERIFY_ALIAS_IDENTITY,
    ActionConfirmations,
    Alias,
    Aliases,
    AliasIdentityWitness,
    Anchor,
    Assessment,
    BatchResult,
    BoundClaim,
    BoundClaims,
    BoundDraft,
    BoundRepairs,
    Claim,
    Claims,
    Finding,
    IdentifiedClaim,
    LocatedMention,
    MentionInput,
    Repairs,
    UnboundRelationship,
    Verdicts,
    VerifiedAlias,
    cross_references,
    normalized,
)
from domain_kernel.discovery.application.claim_graph import (
    ClaimGraph,
    ambiguous_concept_names,
    assemble_claims,
    include_verified_evidence,
    proposal_names,
)
from domain_kernel.discovery.application.field_verification import assess
from domain_kernel.discovery.application.passage_ranking import rank_passages
from domain_kernel.discovery.application.ports import SchemaDiscoveryGateway
from domain_kernel.discovery.application.structured_output import output_error, response_schema
from domain_kernel.discovery.domain.schema_policy import (
    COMPACT_DRAFT_STAGE,
    COMPACT_ORIENTATION_STAGE,
    COMPACT_REPAIR_STAGE,
    COMPACT_STAGES,
    DISCOVERY_STAGE_ATTEMPTS,
    DISCOVERY_STAGE_TIMEOUT_SECONDS,
)
from domain_kernel.discovery.infrastructure import openai_decisions
from domain_kernel.discovery.infrastructure.checkpoints import (
    Checkpoint,
    Receipt,
    StageCheckpoints,
    write_private,
)
from domain_kernel.discovery.infrastructure.local_replay import LocalReplayGateway
from domain_kernel.shared.application.inference import (
    InferenceInput,
    InferenceTimeoutError,
    ModelGateway,
    ModelRequest,
    ModelResponse,
    TruncatedResponse,
    TruncatedResponseError,
)
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.naming import LOOKUP_NAME_PATTERN
from domain_kernel.shared.domain.record_encoding import record_value
from domain_kernel.shared.errors import InferenceError, MissingCapabilityError
from domain_kernel.shared.hashing import canonical_json_bytes, hash_json
from domain_kernel.shared.validation import require_exact, require_text
from domain_kernel.sources.domain.parsed import DocumentSpan

if TYPE_CHECKING:
    from collections.abc import (
        Awaitable,
        Callable,
        Coroutine,
        Iterable,
        Iterator,
        Mapping,
        Sequence,
    )
    from pathlib import Path

    from domain_kernel.discovery.infrastructure.litellm_gateway import LiteLLMGateway
    from domain_kernel.discovery.infrastructure.mentions import NamedEntityHints
    from domain_kernel.sources.domain.models import SourceRevision


class _Approved(BaseModel):
    name: str
    meaning: str
    kind: str | None = None


class _Context(BaseModel):
    approved_meanings: tuple[_Approved, ...] = ()


_MAX_ENDPOINT_CONCURRENCY = 3
_BROAD_OMISSION_TIMEOUT = "Broad omission work deferred because a request timed out."


class _StageFrameLimitError(InferenceError):
    """A stage exceeded the serialized request budget before dispatch."""


def _omission_failure(error: InferenceError | TimeoutError) -> str:
    if isinstance(error, TimeoutError):
        return "Omission window timed out during coverage."
    if error.issue is not None:
        return error.issue.message
    return "Omission window inference was interrupted or unavailable."


class _State(TypedDict):
    batches: list[BatchResult]


class _Runnable(Protocol):
    async def ainvoke(self, state: _State, /) -> object: ...


class _Builder(Protocol):
    def add_node(self, name: str, node: Callable[[_State], Awaitable[_State]], /) -> object: ...
    def add_edge(self, start: str, end: str, /) -> object: ...
    def compile(self) -> _Runnable: ...


@runtime_checkable
class _LangGraph(Protocol):
    def StateGraph(self, schema: type[_State], /) -> _Builder: ...  # noqa: N802 -- vendor API

    @property
    def START(self) -> str: ...  # noqa: N802 -- vendor API

    @property
    def END(self) -> str: ...  # noqa: N802 -- vendor API


async def _complete_batches[T](
    calls: Iterable[Coroutine[object, object, T]],
) -> list[T]:
    tasks = [asyncio.create_task(call) for call in calls]
    try:
        return list(await asyncio.gather(*tasks))
    finally:
        for task in tasks:
            if not task.done():
                _ = task.cancel()
        _ = await asyncio.gather(*tasks, return_exceptions=True)


def _native_pages(part: InferenceInput) -> tuple[int, ...] | None:
    locator = part.evidence[0].locator
    if not isinstance(locator, DocumentSpan) or locator.section is None:
        return None
    match = re.match(r"^docling-chunk/\d+/pages/([\d,]*)/items/", locator.section)
    return None if match is None else tuple(int(n) for n in match[1].split(",") if n)


def _groups(request: ModelRequest, limit: int) -> list[BatchResult]:
    chunks: dict[tuple[object, int], list[str]] = defaultdict(list)
    for part in request.inputs:
        if (pages := _native_pages(part)) and len(pages) == 1:
            chunks[part.evidence[0].source, pages[0]].append(part.text)
    batches: list[BatchResult] = []
    size = 0
    for index, part in enumerate(request.inputs, start=1):
        evidence = part.evidence[0]
        if len(part.evidence) != 1:
            raise InferenceError(message="Staged extraction requires one locator per passage.")
        loc = evidence.locator
        if (
            _native_pages(part) is None
            and isinstance(loc, DocumentSpan)
            and loc.page is not None
            and loc.section is None
            and (matches := chunks.get((evidence.source, loc.page)))
            and normalized(part.text) in normalized("\n".join(matches))
        ):
            continue
        cost = len(part.text.encode())
        if cost > limit:
            raise InferenceError(
                message="An atomic passage exceeds the batch limit. Reduce the Docling chunk size."
            )
        if not batches or size + cost > limit:
            batches.append(BatchResult(passages=[]))
            size = 0
        batches[-1].passages.append(index)
        size += cost
    return batches


_VERIFICATION_GROUP = 3
_RECOVERY_VERIFICATION_GROUP = 18
_RECOVERY_FOCUS_LIMIT = 14
_RECOVERY_WINDOW_SIZE = 7
_RECOVERY_WINDOW_LIMIT = 2
_RECOVERY_CALL_LIMIT = 4
_RECOVERY_CONTEXT_LIMIT = 20
_RECOVERY_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_RECOVERY_QUALIFIER = re.compile(r"\b(?:unless|except|only|before|after|until|or)\b", re.IGNORECASE)
_TARGETED_RECOVERY = (
    "Recover the explicitly missing endpoint definitions and in-scope facts in the focus excerpts. "
    "Use the supplied evidence and verified claims to avoid paraphrasing existing assertions. "
    "Look for missing specific participants, named facts, coordinated recipients, quantities, "
    "and conditions or exceptions. Preserve direction and the full condition. A focused excerpt "
    "is a lead; use surrounding text from the cited passage when needed. For a missing endpoint, "
    "use its requested lookup name only if the source supports that specific definition. "
    "Return at most 12 new claims; leave uncertain mappings unresolved. "
)
_CONTEXT_PASSAGES = 3
_ALIAS_GROUP_LIMIT = 24
_MIN_ALIAS_TOKEN = 3


def _local_claim(claim: IdentifiedClaim, indexes: list[int]) -> IdentifiedClaim:
    local = claim.model_copy(deep=True)
    for qualified in (local, *local.conditions, *local.exceptions):
        qualified.evidence = [
            anchor.model_copy(update={"citation": indexes.index(anchor.citation) + 1})
            for anchor in qualified.evidence
        ]
    if isinstance(local, BoundClaim):
        for qualifier in local.qualifiers:
            qualifier.evidence = [
                anchor.model_copy(update={"citation": indexes.index(anchor.citation) + 1})
                for anchor in qualifier.evidence
            ]

        def local_mention(mention: LocatedMention | None) -> LocatedMention | None:
            if mention is None:
                return None
            anchor = mention.anchor.model_copy(
                update={"citation": indexes.index(mention.anchor.citation) + 1}
            )
            identity = mention.identity_witness
            if identity is not None:
                identity = identity.model_copy(
                    update={"citation": indexes.index(identity.citation) + 1}
                )
            return mention.model_copy(update={"anchor": anchor, "identity_witness": identity})

        local.mention = local_mention(local.mention)
        local.subject = local_mention(local.subject)
        local.object = local_mention(local.object)
    return local


def _edge_context(*, text: str, quotes: Iterable[str]) -> str:
    """Restore bounded surroundings for elliptical quotes while keeping the original locator."""
    passage = normalized(text)
    intervals: list[tuple[int, int]] = []
    for raw_quote in quotes:
        quote = normalized(raw_quote)
        start = passage.index(quote)
        # The locator identifies a passage, not a character offset. Let the verifier see
        # both readings when an anchor alone cannot identify an occurrence.
        if passage.find(quote, start + 1) >= 0:
            return passage
        intervals.append((max(0, start - 240), min(len(passage), start + len(quote) + 240)))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return "\n[…]\n".join(passage[start:end] for start, end in merged)


@dataclass(frozen=True, slots=True)
class _EndpointReview:
    snippets: list[InferenceInput]
    instruction: str


def _endpoint_packet(
    *,
    claim: IdentifiedClaim,
    original: IdentifiedClaim,
    frame: dict[str, object],
    meanings: Mapping[str, str],
    original_meanings: Mapping[str, str],
) -> dict[str, object]:
    packet: dict[str, object] = {
        "edge": frame,
        "subject_meaning": meanings.get(claim.source or ""),
        "target_meaning": meanings.get(claim.target or ""),
    }
    if (original.source, original.target) != (claim.source, claim.target):
        packet["source_wording_before_reconciliation"] = {
            "subject": original.source,
            "target": original.target,
            "subject_meaning": original_meanings.get(original.source or ""),
            "target_meaning": original_meanings.get(original.target or ""),
        }
    return packet


def _endpoint_groups(
    edges: list[IdentifiedClaim],
    *,
    originals: Mapping[str, IdentifiedClaim],
    size: int,
    fields: bool,
) -> Iterator[tuple[bool, list[IdentifiedClaim]]]:
    groups: dict[bool, list[IdentifiedClaim]] = defaultdict(list)
    for edge in edges:
        original = originals[edge.claim_id]
        collapsed = fields and edge.source == edge.target and original.source != original.target
        groups[collapsed].append(edge)
    for collapsed, items in groups.items():
        for start in range(0, len(items), size):
            yield collapsed, items[start : start + size]


def _term_words(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", plain))


def _evidence_clauses(quote: str) -> list[str]:
    return [
        f" {_term_words(part)} " for part in re.split(r"[.!?;\u3002\uff01\uff1f\uff1b\n]+", quote)
    ]


def _distinct_designations(*, first: Claim, second: Claim, quote: str) -> bool:
    text = _term_words(quote)

    def mentions(claim: Claim) -> set[tuple[int, int]]:
        terms = {_term_words(claim.name), _term_words(claim.title)}
        if isinstance(claim, BoundClaim) and claim.mention is not None:
            terms.add(_term_words(claim.mention.anchor.quote))
        return {
            occurrence.span()
            for term in terms
            if term
            for occurrence in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text)
        }

    return any(
        first_end <= second_start or second_end <= first_start
        for first_start, first_end in mentions(first)
        for second_start, second_end in mentions(second)
    )


def _designations(*, claim: Claim) -> tuple[str, ...]:
    names = (claim.title, claim.name)
    if isinstance(claim, BoundClaim) and claim.mention is not None:
        names = (claim.title, claim.preferred_name, claim.mention.anchor.quote)
    return tuple(_term_words(name) for name in names)


def _alias_groups(concepts: Mapping[str, Claim]) -> Iterator[list[Claim]]:
    groups: dict[str, list[str]] = defaultdict(list)
    evidence: dict[tuple[int, str, int], list[str]] = defaultdict(list)
    shared: dict[tuple[int, str], list[str]] = defaultdict(list)
    for name in sorted(concepts):
        claim = concepts[name]
        anchor = claim.evidence[0]
        label = claim.preferred_name if isinstance(claim, BoundClaim) else name
        term = _term_words(label)
        if term and f" {term} " in f" {_term_words(anchor.quote)} ":
            shared[anchor.citation, anchor.quote].append(name)
        for index, sentence in enumerate(_evidence_clauses(anchor.quote)):
            if term and f" {term} " in sentence:
                evidence[anchor.citation, anchor.quote, index].append(name)
        for token in sorted(set(label.split("-"))):
            if len(token) >= _MIN_ALIAS_TOKEN:
                groups[token].append(name)
    offered: set[tuple[str, str]] = set()
    for group in _bounded_alias_groups((*groups.values(), *evidence.values())):
        offered.update((first, second) for first, second in combinations(group, 2))
        yield [concepts[name] for name in group]
    for group in _bounded_alias_groups(shared.values()):
        pairs = {(first, second) for first, second in combinations(group, 2)}
        if pairs - offered:
            offered.update(pairs)
            yield [concepts[name] for name in group]


def _bounded_alias_groups(groups: Iterable[list[str]]) -> Iterator[list[str]]:
    seen: set[tuple[str, ...]] = set()
    for names in groups:
        key = tuple(names)
        if key in seen:
            continue
        seen.add(key)
        for start in range(0, len(names), _ALIAS_GROUP_LIMIT):
            group = names[start : start + _ALIAS_GROUP_LIMIT]
            if len(group) > 1:
                yield group


def _closed_components(rows: Sequence[Claim]) -> list[list[str]]:
    neighbors = {row.name: set[str]() for row in rows if row.kind == "concept"}
    for row in rows:
        if row.source in neighbors and row.target in neighbors and row.source and row.target:
            neighbors[row.source].add(row.target)
            neighbors[row.target].add(row.source)
    groups: list[list[str]] = []
    remaining = set(neighbors)
    while remaining:
        pending = [min(remaining)]
        visited: set[str] = set()
        while pending:
            vertex = pending.pop()
            if vertex not in visited:
                visited.add(vertex)
                pending.extend(neighbors[vertex] - visited)
        groups.append(sorted(visited))
        remaining -= visited
    return groups


class DiscoveryStage(StrEnum):
    """Inference tasks that can use independent model settings."""

    EXTRACT = "extract"
    COVERAGE = "coverage"
    VERIFY = "verify"
    REPAIR = "repair"
    RECONCILE = "reconcile"
    ALIAS_PROOF = "alias_proof"
    ENDPOINTS = "endpoints"
    SELF_ACTION = "self_action"
    HELD_REPAIR = "held_repair"
    HELD_VERIFY = "held_verify"
    FOCUSED_OMISSIONS = "focused_omissions"
    SCHEMA_MAPPING = schema_evidence.MAPPING_STAGE
    SCHEMA_COMPACT_ORIENTATION = COMPACT_ORIENTATION_STAGE
    SCHEMA_COMPACT_DRAFT = COMPACT_DRAFT_STAGE
    SCHEMA_COMPACT_REPAIR = COMPACT_REPAIR_STAGE


@dataclass(frozen=True, kw_only=True)
class DiscoveryStageRoute:
    """A model gateway and its versioned provider settings for one stage."""

    gateway: ModelGateway | None
    profile: str

    def __post_init__(self) -> None:
        """Require a replay identity for the provider and its settings."""
        require_text(value=self.profile, field="Versioned stage provider configuration")


@dataclass(frozen=True, kw_only=True)
class LangGraphDiscoveryGateway(ModelGateway):
    """Process a scoped discovery request with local, resumable stage receipts.

    Use a private directory per tenant and a profile identifying the underlying
    endpoint, model and inference settings. Retained stage responses enable replay.
    The stage timeout caps each provider call within the client's inference budget.
    """

    gateway: ModelGateway | None
    directory: Path
    profile: str
    batch_bytes: int = 48_000
    concurrency: int = 3
    max_request_bytes: int = 512_000
    mention_detector: NamedEntityHints | None = None
    retain_responses: bool = True
    verification: Literal["aggregate", "fields"] = "aggregate"
    stage_timeout_seconds: float | None = None
    stage_max_attempts: int | None = None
    preserve_split_context: bool = False
    evidence_bound: bool | None = None
    binding_version: Literal["v1", "v2", "v3"] | None = None
    targeted_recovery: bool = False
    proposal_batching: bool = False
    held_endpoint_repair: bool = False
    focused_omission_recovery: bool = False
    scope_shadow: bool = False
    decisions_enabled: bool | None = None
    resumable_omissions: bool = False
    deferred_omissions_use_provider_limit: bool = False
    endpoint_concurrency: int = 1
    stage_routes: Mapping[DiscoveryStage, DiscoveryStageRoute] = field(
        default_factory=dict[DiscoveryStage, DiscoveryStageRoute], hash=False
    )

    def __post_init__(self) -> None:
        """Validate the bounds before opening a journal or scheduling work."""
        if self.verification not in ("aggregate", "fields"):
            raise ValueError("Choose aggregate or fields verification.")
        if self.evidence_bound and self.verification != "aggregate":
            raise ValueError("Use aggregate verification for evidence-bound discovery.")
        if self.binding_version not in (None, "v1", "v2", "v3"):
            raise ValueError("Choose a supported evidence binding version.")
        if self.batch_proposals and _source_identity_policy(config=self) is None:
            raise ValueError(
                "Use proposal batching or targeted recovery with default aggregate discovery."
            )
        self._check_recovery_profile()
        if type(self.batch_bytes) is not int or self.batch_bytes < 1:
            raise ValueError("Set a positive batch byte limit.")
        if type(self.max_request_bytes) is not int or self.max_request_bytes <= 0:
            raise ValueError("Set a positive serialized request limit.")
        if type(self.concurrency) is not int or self.concurrency < 1:
            raise ValueError("Set positive inference concurrency.")
        self._normalize_stage_timeout()
        routes = dict(self.stage_routes)
        for stage, route in routes.items():
            require_exact(value=stage, expected=DiscoveryStage, field="Discovery stage")
            require_exact(value=route, expected=DiscoveryStageRoute, field="Stage route")
        object.__setattr__(self, "stage_routes", MappingProxyType(routes))

    def _normalize_stage_timeout(self) -> None:
        if (timeout := self.stage_timeout_seconds) is None:
            return
        if type(timeout) not in (int, float) or not 0 < timeout < inf:
            raise ValueError("Set a positive finite stage timeout in seconds.")
        object.__setattr__(self, "stage_timeout_seconds", float(timeout))

    def _check_recovery_profile(self) -> None:
        if self.stage_max_attempts is not None and (
            type(self.stage_max_attempts) is not int or self.stage_max_attempts < 1
        ):
            raise ValueError("Allow at least one provider attempt per discovery stage request.")
        require_exact(value=self.preserve_split_context, expected=bool, field="Split context")
        if self.decisions_enabled is not None:
            require_exact(value=self.decisions_enabled, expected=bool, field="Endpoint Decisions")
        if self.scope_shadow and not self.retain_responses:
            raise ValueError("Retain the private discovery audit to use scope shadow mode.")
        if self.deferred_omissions_use_provider_limit and not self.resumable_omissions:
            raise ValueError("Use resumable omissions to change the deferred window output limit.")
        if self.held_endpoint_repair and (not self.proposal_batching or self.targeted_recovery):
            raise ValueError("Use held endpoint repair with proposal batching and broad coverage.")
        if self.resumable_omissions and (
            not self.proposal_batching or self.targeted_recovery or not self.retain_responses
        ):
            raise ValueError(
                "Use resumable omissions with retained receipts, batching and broad coverage."
            )
        if self.focused_omission_recovery and (
            not self.proposal_batching or self.targeted_recovery or not self.retain_responses
        ):
            raise ValueError(
                "Use focused omissions with retained receipts, batching and broad coverage."
            )
        if (
            type(self.endpoint_concurrency) is not int
            or not 1 <= self.endpoint_concurrency <= _MAX_ENDPOINT_CONCURRENCY
        ):
            raise ValueError("Use between one and three concurrent endpoint groups.")

    @property
    def batch_proposals(self) -> bool:
        """Store proposals in bounded batches under one draft."""
        return self.targeted_recovery or self.proposal_batching

    @property
    def binding_contract(self) -> str | None:
        """Select the requested evidence-bound relationship contract."""
        if self.verification != "aggregate" or self.evidence_bound is False:
            return None
        if self.binding_version is None:
            return endpoint_contract.VERSION if self.evidence_bound is True else None
        if self.binding_version == "v3":
            return endpoint_contract.REPAIR_VERSION
        return (
            endpoint_contract.VERSION if self.binding_version == "v2" else evidence_binding.VERSION
        )

    @property
    def decisions_active(self) -> bool:
        """Use Decisions only for the built-in direct OpenAI workflow or explicit replay."""
        if self.decisions_enabled is False or _source_identity_policy(config=self) is None:
            return False
        if _decision_provider(config=self) is not None:
            return True
        return (
            self.decisions_enabled is True
            and self.gateway is None
            and all(route.gateway is None for route in self.stage_routes.values())
        )

    @property
    def supports_schema_discovery(self) -> bool:
        """Accept the current stages on their effective provider or replay routes."""
        for stage in (*COMPACT_STAGES, schema_evidence.MAPPING_STAGE):
            route = self.stage_routes.get(DiscoveryStage(stage))
            gateway = self.gateway if route is None else route.gateway
            if gateway is not None and (
                not isinstance(gateway, SchemaDiscoveryGateway)
                or not gateway.supports_schema_discovery
            ):
                return False
        return True

    @property
    def discovery_stage_attempts(self) -> int:
        """Allow the SDK to honor a stricter host retry budget."""
        return self.stage_max_attempts or DISCOVERY_STAGE_ATTEMPTS

    @property
    def standalone_timeout(self) -> float:
        """Return the deadline used by the standalone proposal extractor."""
        return self.stage_timeout_seconds or 300.0

    @property
    def discovery_profile(self) -> str | None:
        """Pin the workflow policy, provider, and request bounds for resumable discovery."""
        contract = _source_identity_policy(config=self) or self.binding_contract
        if contract is None or contract == evidence_binding.VERSION:
            return None
        return hash_json(
            value=record_value(
                value=(
                    contract,
                    self.profile,
                    self.batch_bytes,
                    self.max_request_bytes,
                    self.standalone_timeout,
                    tuple(
                        sorted(
                            (stage.value, route.profile)
                            for stage, route in self.stage_routes.items()
                        )
                    ),
                    (self.mention_detector.profile, self.mention_detector.labels)
                    if self.mention_detector is not None
                    else None,
                    *(
                        ("proposal-batching-v1",)
                        if self.proposal_batching and not self.targeted_recovery
                        else ()
                    ),
                    *((held_endpoints.VERSION,) if self.held_endpoint_repair else ()),
                    *((omission_windows.VERSION,) if self.resumable_omissions else ()),
                    *((focused_omissions.VERSION,) if self.focused_omission_recovery else ()),
                    *(("adjacent-split-context-v1",) if self.preserve_split_context else ()),
                    *((self.endpoint_concurrency,) if self.endpoint_concurrency != 1 else ()),
                    *((openai_decisions.PROFILE,) if self.decisions_active else ()),
                ),
            ),
        ).value

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        if request.provider_stage in (*COMPACT_STAGES, schema_evidence.MAPPING_STAGE):
            return await self._generate_schema(
                request=request, stage=DiscoveryStage(request.provider_stage)
            )
        try:
            api = import_module("langgraph.graph")
        except ImportError:
            raise MissingCapabilityError(message="Install the discovery-workflow extra.") from None
        if not isinstance(api, _LangGraph):
            raise MissingCapabilityError(message="Install a compatible LangGraph workflow extra.")
        if request.response_schema_json != response_schema():
            raise InferenceError(message="Select the staged executor matching the proposal schema.")
        execution = _Execution(config=self, request=request)
        graph = api.StateGraph(_State)
        stages = self._stages(execution=execution)
        state: _State = {"batches": _groups(request, self.batch_bytes)}
        saved = await execution.restore()
        previous = api.START
        for name, node in stages:
            if saved is not None:
                if name == saved.stage:
                    state = {"batches": saved.batches}
                    saved = None
                continue
            _ = graph.add_node(name, execution.checkpointed(name, node))
            _ = graph.add_edge(previous, name)
            previous = name
        if saved is not None:
            raise InferenceError(message="Unknown stage in the saved graph checkpoint.")
        if previous != api.START:
            _ = graph.add_edge(previous, api.END)
            state = _STATE.validate_python(await graph.compile().ainvoke(state))
        return await asyncio.to_thread(execution.finish, batches=state["batches"])

    async def _generate_schema(
        self, *, request: ModelRequest, stage: DiscoveryStage
    ) -> ModelResponse:
        if not self.supports_schema_discovery:
            raise MissingCapabilityError(message="Use a schema-capable discovery gateway.")
        envelope = (
            request.instructions,
            request.context_json,
            request.response_schema_json,
            tuple(item.text for item in request.inputs),
        )
        if len(canonical_json_bytes(value=record_value(value=envelope))) > self.max_request_bytes:
            raise InferenceError(message="The schema modeling request exceeds the SDK byte limit.")
        route = self.stage_routes.get(stage)
        profile = self.profile if route is None else route.profile
        return await LocalReplayGateway(
            path=self.directory / "schema-stages.sqlite3",
            # This is a journal namespace, not the workflow policy version.
            profile=f"{profile}/schema-discovery-v1/{stage.value}",
            gateway=self.gateway if route is None else route.gateway,
            retain_responses=self.retain_responses,
            max_attempts=1,
        ).generate(
            request=replace(
                request,
                timeout_seconds=min(
                    request.timeout_seconds,
                    self.stage_timeout_seconds or DISCOVERY_STAGE_TIMEOUT_SECONDS,
                ),
            )
        )

    def _stages(
        self, *, execution: _Execution
    ) -> tuple[tuple[str, Callable[[_State], Awaitable[_State]]], ...]:
        initial = (("extract", execution.extract),)
        verification = (("verify", execution.verify), ("repair", execution.repair))
        coverage = (("coverage", execution.coverage),)
        final = (("reconcile", execution.reconcile), ("edges", execution.check_edges))
        stages = (
            (*initial, *verification, ("targeted-coverage", execution.targeted_coverage), *final)
            if self.targeted_recovery
            else (*initial, *coverage, *verification, *final)
        )
        if execution.request.discovery_continuation:
            if not self.resumable_omissions:
                raise InferenceError(message="Use the original resumable discovery profile.")
            stages = (("coverage-continuation", execution.continue_coverage), *verification, *final)
        if self.held_endpoint_repair:
            stages = (*stages, ("held-endpoints", execution.recover_held_endpoints))
        if self.focused_omission_recovery and not execution.request.discovery_continuation:
            stages = (*stages, ("focused-omissions", execution.recover_focused_omissions))
        return stages


_STATE = TypeAdapter(_State)


def _source_identity_policy(*, config: LangGraphDiscoveryGateway) -> str | None:
    if (
        config.verification == "aggregate"
        and config.evidence_bound is None
        and config.binding_version is None
    ):
        return "targeted-recovery-v3" if config.targeted_recovery else "legacy-source-identity-v1"
    return None


def _decision_provider(*, config: LangGraphDiscoveryGateway) -> LiteLLMGateway | None:
    if config.gateway is None and DiscoveryStage.ENDPOINTS not in config.stage_routes:
        return None
    primary = [] if config.gateway is None else [config.gateway]
    return openai_decisions.official_provider(
        [*primary, *(route.gateway for route in config.stage_routes.values())]
    )


@final
class _Execution:
    def __init__(self, *, config: LangGraphDiscoveryGateway, request: ModelRequest) -> None:
        self.config = config
        self.request = request
        contract = config.binding_contract or ""
        self.source_identity_policy = _source_identity_policy(config=config)
        self.stable_binding = contract == endpoint_contract.VERSION
        self.repaired_binding = contract == endpoint_contract.REPAIR_VERSION
        self.uses_mention_table = bool(contract) and not self.repaired_binding
        self.repair_index = (
            endpoint_repair.EndpointIndex(inputs=request.inputs) if self.repaired_binding else None
        )
        self.alias_index = self.repair_index
        if self.source_identity_policy:
            self.alias_index = endpoint_repair.EndpointIndex(inputs=request.inputs)
        self.recording = LocalReplayGateway(
            path=config.directory / "stages.sqlite3",
            profile=f"{config.profile}/{contract}" if contract else config.profile,
            gateway=config.gateway,
            retain_responses=config.retain_responses,
            max_attempts=config.stage_max_attempts or 1,
        )
        self.stage_recordings = {
            stage: LocalReplayGateway(
                path=config.directory / "stage-routes.sqlite3",
                profile=hash_json(
                    value=(stage.value, route.profile, contract)
                    if contract
                    else (stage.value, route.profile)
                ).value,
                gateway=route.gateway,
                retain_responses=config.retain_responses,
                max_attempts=config.stage_max_attempts or 1,
            )
            for stage, route in config.stage_routes.items()
        }
        routing = tuple(
            sorted((stage.value, r.profile) for stage, r in config.stage_routes.items())
        )
        self.slots = asyncio.Semaphore(config.concurrency)
        self.receipts: list[Receipt] = []
        self.decisions_audit: endpoint_decisions.Audit | None = None
        self.decisions_gate: openai_decisions.Gate | None = None
        if config.decisions_active:
            provider = _decision_provider(config=config)
            self.decisions_gate = openai_decisions.Gate(
                journal=LocalReplayGateway(
                    path=config.directory / "endpoint-decisions.sqlite3",
                    profile=openai_decisions.PROFILE,
                    gateway=None
                    if provider is None
                    else openai_decisions.Gateway(api_key=provider.api_key),
                    retain_responses=config.retain_responses,
                ),
                slots=self.slots,
                max_request_bytes=config.max_request_bytes,
                stage_timeout_seconds=config.standalone_timeout,
            )
        self.held_recovery = held_endpoints.Recovery()
        self.omission_windows: list[omission_windows.WindowReceipt] = []
        self._broad_omission_timed_out = False
        self._deferred_omissions_use_provider_limit = (
            bool(request.discovery_continuation) and config.deferred_omissions_use_provider_limit
        )
        self.focused_omissions: list[focused_omissions.FollowUp] = []
        self.omission_calls: dict[SourceRevision, int] = defaultdict(int)
        self.started = monotonic()
        intent = hash_json(
            value=record_value(
                value=(
                    "document-graph-v15-alias-proof",
                    *(("adjacent-split-context-v1",) if config.preserve_split_context else ()),
                    *((openai_decisions.PROFILE,) if config.decisions_active else ()),
                    *((self.source_identity_policy,) if self.source_identity_policy else ()),
                    *((_TARGETED_RECOVERY,) if config.targeted_recovery else ()),
                    *(
                        (
                            omission_windows.VERSION,
                            request.discovery_continuation,
                            request.discovery_pending_concepts,
                        )
                        if config.resumable_omissions
                        else ()
                    ),
                    *(
                        ("deferred-omissions-provider-output-limit",)
                        if self._deferred_omissions_use_provider_limit
                        else ()
                    ),
                    *(
                        (
                            held_endpoints.VERSION,
                            request.approved_concept_aliases,
                            request.approved_concept_pins,
                            request.discovery_output_bytes,
                        )
                        if config.held_endpoint_repair
                        else ()
                    ),
                    *(
                        (
                            focused_omissions.VERSION,
                            focused_omissions.EXTRACT,
                            focused_omissions.VERIFY,
                            focused_omissions.ENDPOINTS,
                            request.discovery_output_bytes,
                        )
                        if config.focused_omission_recovery
                        else ()
                    ),
                    config.verification,
                    (
                        aggregate_verification.VERIFY,
                        aggregate_verification.CHECK_EDGES,
                        json.dumps(aggregate_verification.Verdicts.model_json_schema()),
                    )
                    if config.verification == "aggregate"
                    else None,
                    (
                        INITIAL_EXTRACTION,
                        EXTRACT,
                        OMISSIONS,
                        VERIFY,
                        REPAIR,
                        RECONCILE,
                        VERIFY_ALIAS_IDENTITY,
                        CHECK_EDGES,
                        ALIGNED_ENDPOINTS,
                        COLLAPSED_ENDPOINTS,
                        CONFIRM_SELF_ACTION,
                    ),
                    tuple(
                        json.dumps(schema.model_json_schema())
                        for schema in (
                            Claims,
                            Verdicts,
                            Aliases,
                            AliasIdentityWitness,
                            Repairs,
                            ActionConfirmations,
                        )
                    ),
                    request.request_id,
                    request.scope,
                    config.profile,
                    config.batch_bytes,
                    config.max_request_bytes,
                    request.instructions,
                    request.context_json,
                    request.response_schema_json,
                    None
                    if config.mention_detector is None
                    else (config.mention_detector.profile, config.mention_detector.labels),
                    tuple((p.text, p.evidence) for p in request.inputs),
                    *((routing,) if routing else ()),
                    *(
                        (
                            contract,
                            evidence_binding.MINING,
                            evidence_binding.CHECK,
                            json.dumps(BoundClaims.model_json_schema()),
                            json.dumps(BoundRepairs.model_json_schema()),
                            *(
                                (
                                    endpoint_contract.VERIFY_ENDPOINTS,
                                    endpoint_contract.MINING,
                                    json.dumps(
                                        endpoint_contract.EndpointVerdicts.model_json_schema()
                                    ),
                                    request.approved_concept_pins,
                                )
                                if self.stable_binding
                                else ()
                            ),
                        )
                        if contract
                        else ()
                    ),
                )
            )
        )
        self.checkpoint_key = intent.value.removeprefix("sha256:")
        self.checkpoints = StageCheckpoints(
            directory=config.directory / "checkpoints", key=self.checkpoint_key
        )
        self.aliases: dict[str, Alias | VerifiedAlias] = {}
        self.edge_findings: dict[str, Finding] = {}
        self.endpoint_evidence: dict[str, list[Anchor]] = {}
        self.approved = {
            item.name
            for item in _Context.model_validate_json(request.context_json or "{}").approved_meanings
            if item.kind == "concept"
        }
        self.pending_concepts = {
            name: (identity, meaning)
            for name, identity, meaning in request.discovery_pending_concepts
            if name not in self.approved
        }
        self.approved_keys = {
            name: endpoint_contract.approved_key(identity=identity, revision=revision)
            for name, identity, revision in request.approved_concept_pins
            if name in self.approved
        }
        self.pages: dict[tuple[object, int], int] = {}
        for i, part in enumerate(request.inputs, 1):
            evidence = part.evidence[0]
            loc = evidence.locator
            if isinstance(loc, DocumentSpan) and loc.section is None and loc.page is not None:
                self.pages[evidence.source, loc.page] = i

    async def restore(self) -> Checkpoint | None:
        if not self.config.retain_responses:
            return None
        saved = await asyncio.to_thread(self.checkpoints.load)
        if saved is not None:
            self.receipts = saved.receipts
            self.aliases = saved.aliases
            self.edge_findings = saved.edge_findings
            self.endpoint_evidence = saved.endpoint_evidence
            self.held_recovery = saved.held_recovery
            self.omission_windows = saved.omission_windows
            self.focused_omissions = saved.focused_omissions
            self.decisions_audit = saved.endpoint_decisions
        return saved

    def checkpointed(
        self, name: str, node: Callable[[_State], Awaitable[_State]]
    ) -> Callable[[_State], Awaitable[_State]]:
        async def checkpoint(state: _State) -> _State:
            result = await node(state)
            if self.config.retain_responses:
                snapshot = Checkpoint(
                    stage=name,
                    batches=result["batches"],
                    receipts=self.receipts,
                    aliases=self.aliases,
                    edge_findings=self.edge_findings,
                    endpoint_evidence=self.endpoint_evidence,
                    held_recovery=self.held_recovery,
                    omission_windows=self.omission_windows,
                    focused_omissions=self.focused_omissions,
                    endpoint_decisions=self.decisions_audit,
                )
                await asyncio.to_thread(self.checkpoints.save, checkpoint=snapshot)
            return result

        return checkpoint

    def part(self, index: int) -> InferenceInput:
        return self.request.inputs[index - 1]

    async def call[T: BaseModel](  # noqa: PLR0913 - Explicit stage and inference frame fields.
        self,
        *,
        stage: DiscoveryStage,
        schema: type[T],
        prompt: str,
        indexes: list[int],
        context: dict[str, object],
        inputs: Sequence[InferenceInput] | None = None,
        output_tokens: int | None = None,
        use_provider_output_limit: bool = False,
    ) -> T:
        context["model_context"] = json.loads(self.request.context_json or "{}")
        held_stage = stage in (DiscoveryStage.HELD_REPAIR, DiscoveryStage.HELD_VERIFY)
        request = replace(
            self.request,
            provider_stage=stage.value,
            instructions=prompt,
            inputs=tuple(self.part(i) for i in indexes) if inputs is None else inputs,
            context_json=json.dumps(context, ensure_ascii=False, sort_keys=True),
            response_schema_json=json.dumps(schema.model_json_schema()),
            retry_cancelled=stage in (DiscoveryStage.ENDPOINTS, DiscoveryStage.SELF_ACTION)
            and self.config.endpoint_concurrency > 1,
            use_provider_output_limit=use_provider_output_limit,
            max_output_tokens=None
            if use_provider_output_limit
            else held_endpoints.OUTPUT_TOKENS
            if held_stage
            else output_tokens
            if output_tokens is not None
            else self.request.max_output_tokens,
            timeout_seconds=min(self.request.timeout_seconds, self.config.standalone_timeout),
        )
        envelope = record_value(
            value=(
                request.instructions,
                request.context_json,
                request.response_schema_json,
                tuple((p.text, p.evidence) for p in request.inputs),
            )
        )
        if len(canonical_json_bytes(value=envelope)) > self.config.max_request_bytes:
            message = f"The {stage.value} request exceeds the SDK byte limit."
            raise _StageFrameLimitError(
                message=message,
                issue=Issue(code="stage_frame_limit", path=(stage.value,), message=message),
            )
        async with self.slots:
            recording = self.stage_recordings.get(stage, self.recording)
            try:
                response = await recording.generate(request=request)
            except TruncatedResponseError as error:
                self._record_usage(response=error.response, stage=stage)
                raise
        self._record_usage(response=response, stage=stage)
        if (
            held_stage
            and response.output_tokens is not None
            and response.output_tokens > held_endpoints.OUTPUT_TOKENS
        ):
            raise InferenceError(message="Held endpoint response exceeded its token budget.")
        try:
            return schema.model_validate_json(response.output_json)
        except ValidationError as exc:
            err = exc.errors(include_input=False, include_context=False, include_url=False)[0]
            loc = tuple(
                p
                if type(p) is int
                or p
                in {
                    "claims",
                    "claim_id",
                    "actor",
                    "object",
                    "recipient",
                    "modality",
                    "verdicts",
                    "evidence",
                    "citation",
                    "quote",
                    "source",
                    "target",
                    "index",
                    "name",
                    "kind",
                    "meaning",
                    "title",
                    "conditions",
                    "exceptions",
                    "text",
                    "status",
                    "reason",
                }
                else "<field>"
                for p in err["loc"]
            )
            raise output_error(
                code="invalid_stage_response",
                path=loc,
                message=f"Inspect the retained {schema.__name__} response ({err['type']}).",
            ) from None

    def _record_usage(
        self, *, response: ModelResponse | TruncatedResponse, stage: DiscoveryStage
    ) -> None:
        route = self.config.stage_routes.get(stage)
        self.receipts.append(
            Receipt(
                model_id=response.model_id,
                provider_endpoint=response.provider_endpoint,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                stage=stage.value,
                profile=self.config.profile if route is None else route.profile,
            )
        )

    def anchor(self, *, anchor: Anchor, indexes: list[int]) -> Anchor | None:
        quote = normalized(anchor.quote)
        if not quote or not 1 <= anchor.citation <= len(indexes):
            return None
        i = indexes[anchor.citation - 1]
        part = self.part(i)
        if quote not in normalized(part.text):
            return None
        matches = [
            physical
            for page in _native_pages(part) or ()
            if (physical := self.pages.get((part.evidence[0].source, page))) is not None
            and quote in normalized(self.part(physical).text)
        ]
        if matches and (not self.stable_binding or len(matches) == 1):
            return Anchor(citation=matches[0], quote=anchor.quote)
        return Anchor(citation=i, quote=anchor.quote)

    def resolve(self, claim: Claim, indexes: list[int]) -> IdentifiedClaim | None:
        if (
            not re.fullmatch(LOOKUP_NAME_PATTERN, claim.name)
            or not claim.meaning.strip()
            or not claim.title.strip()
        ):
            return None
        if claim.kind == "relationship" and (not claim.source or not claim.target):
            return None
        if claim.kind == "concept" and (claim.source is not None or claim.target is not None):
            return None
        result = claim.model_copy(deep=True)
        for cited in (result, *result.conditions, *result.exceptions):
            resolved = [self.anchor(anchor=a, indexes=indexes) for a in cited.evidence]
            if not resolved or any(a is None for a in resolved):
                return None
            cited.evidence = [a for a in resolved if a is not None]
        if isinstance(result, IdentifiedClaim):
            return result
        return self.identify(result)

    def identify(self, claim: Claim) -> IdentifiedClaim:
        # Passage ordinals belong to one request. Hash resolved source identities instead.
        groups: list[tuple[object, ...]] = []
        for qualified in (claim, *claim.conditions, *claim.exceptions):
            anchors: list[object] = []
            for a in qualified.evidence:
                evidence = self.part(a.citation).evidence[0]
                source = evidence.source
                anchors.append(
                    (
                        source.project_id,
                        source.source_id,
                        source.revision_id,
                        evidence.locator,
                        normalized(a.quote),
                    )
                )
            groups.append(tuple(anchors))
        content = (
            claim.kind,
            claim.name,
            claim.title,
            claim.meaning,
            claim.source,
            claim.target,
            tuple(q.text for q in claim.conditions),
            tuple(q.text for q in claim.exceptions),
            tuple(groups),
        )
        if isinstance(claim, BoundClaim):
            content = (
                *content,
                claim.modality,
                evidence_binding.qualifier_paths(claim.qualifiers),
                tuple((m.id, m.role) for m in (claim.mention, claim.subject, claim.object) if m),
            )
        digest = hash_json(value=record_value(value=content)).value.removeprefix("sha256:")
        return IdentifiedClaim.model_validate(
            {
                **claim.model_dump(include=set(IdentifiedClaim.model_fields)),
                "claim_id": "c-" + digest[:24],
            }
        )

    def _mentions(
        self,
        *,
        rows: Sequence[MentionInput],
        indexes: list[int],
    ) -> dict[str, LocatedMention]:
        counts = Counter(row.ref for row in rows)
        result: dict[str, LocatedMention] = {}
        for row in rows:
            if (
                counts[row.ref] != 1
                or not row.ref.strip()
                or not 1 <= row.anchor.citation <= len(indexes)
            ):
                continue
            index = indexes[row.anchor.citation - 1]
            part = self.part(index)
            canonical = (
                physical
                for page in _native_pages(part) or ()
                if (physical := self.pages.get((part.evidence[0].source, page))) is not None
            )
            located = evidence_binding.locate_mention(
                mention=row,
                index=index,
                part=self.part,
                canonical=canonical,
                approved=self.approved,
                require_unique_source=self.stable_binding,
            )
            if located is not None:
                result[row.ref] = self._bind_approved(mention=located)
        return result

    def _bind_approved(self, *, mention: LocatedMention) -> LocatedMention:
        name = mention.approved_name
        if not self.stable_binding or name is None:
            return mention
        if name not in self.approved_keys:
            return mention.model_copy(update={"approved_name": None})
        index = mention.anchor.citation
        for clause in evidence_binding.identity_clauses(
            quote=self.part(index).text,
            first=(_term_words(mention.anchor.quote),),
            second=(_term_words(name),),
        ):
            return mention.model_copy(
                update={"identity_witness": Anchor(citation=index, quote=clause.strip())}
            )
        return mention.model_copy(update={"approved_name": None})

    def _bind(
        self, *, rows: BoundClaims | BoundRepairs, indexes: list[int]
    ) -> Iterator[tuple[str, BoundClaim | None, str | None]]:
        mentions = self._mentions(rows=rows.mentions, indexes=indexes)
        for row in rows.claims:
            claim = (
                evidence_binding.bind_claim(
                    row=row,
                    mentions=mentions,
                    indexes=indexes,
                    resolve=lambda anchor, passages: self.anchor(anchor=anchor, indexes=passages),
                    identify=self.identify,
                    include_participant_evidence=not self.stable_binding or row.kind == "concept",
                )
                if re.fullmatch(LOOKUP_NAME_PATTERN, row.name)
                else None
            )
            detail = None
            if self.stable_binding and claim is not None and claim.kind == "relationship":
                if not self._supports_participants(claim=claim, evidence=claim.evidence):
                    detail = "The relationship evidence does not locate both exact participants."
                for mention in (claim.subject, claim.object):
                    if (
                        mention
                        and mention.identity_witness
                        and mention.identity_witness not in claim.evidence
                    ):
                        claim.evidence.append(mention.identity_witness)
            yield row.name, claim, detail

    def _supports_participants(self, *, claim: BoundClaim, evidence: Sequence[Anchor]) -> bool:
        return all(
            mention is not None
            and evidence_binding.supports_mention(mention=mention, anchors=evidence, part=self.part)
            for mention in (claim.subject, claim.object)
        )

    async def extract(self, state: _State) -> _State:
        return {
            "batches": await _complete_batches(
                self.mine(batch, i, omissions=False) for i, batch in enumerate(state["batches"])
            )
        }

    def _extraction_instructions(self, *, omissions: bool) -> str:
        return OMISSIONS + EXTRACT if omissions else INITIAL_EXTRACTION

    async def coverage(self, state: _State) -> _State:
        if self.config.resumable_omissions:
            batches: list[BatchResult] = []
            for number, batch in enumerate(state["batches"]):
                if self._broad_omission_timed_out:
                    self._finish_windows(
                        (self._window(i) for i in batch.passages), reason=_BROAD_OMISSION_TIMEOUT
                    )
                    batches.append(batch)
                else:
                    batches.append(await self.mine(batch, number, omissions=True))
            return {"batches": batches}
        return {
            "batches": await _complete_batches(
                self.mine(batch, i, omissions=True) for i, batch in enumerate(state["batches"])
            )
        }

    async def continue_coverage(self, _state: _State) -> _State:
        """Process only the uncompleted intervals from the pinned parent draft."""
        windows: dict[int, list[omission_windows.Window]] = defaultdict(list)
        for citation, start, end in self.request.discovery_continuation:
            window = omission_windows.Window(citation=citation, start=start, end=end)
            part = self.part(citation)
            if not part.is_table and end - start > omission_windows.MAX_CHARS:
                windows[citation].extend(
                    omission_windows.partition(
                        text=part.text, window=window, width=omission_windows.MAX_CHARS
                    )
                )
            else:
                windows[citation].append(window)
        batches: list[BatchResult] = []
        for citation, selected in windows.items():
            batch = BatchResult(passages=[citation])
            await self._process_windows(batch=batch, windows=selected)
            batches.append(batch)
        return {"batches": batches}

    def _window(self, citation: int) -> omission_windows.Window:
        return omission_windows.Window(
            citation=citation, start=0, end=len(self.part(citation).text)
        )

    def _finish_windows(
        self, windows: Iterable[omission_windows.Window], *, reason: str | None
    ) -> None:
        self.omission_windows.extend(
            omission_windows.WindowReceipt(
                citation=w.citation, start=w.start, end=w.end, reason=reason
            )
            for w in windows
        )

    async def _process_windows(
        self, *, batch: BatchResult, windows: list[omission_windows.Window]
    ) -> None:
        pending = list(reversed(windows))
        while pending:
            window = pending.pop()
            parent = self.part(window.citation)
            source = parent.evidence[0].source
            remaining = self.request.timeout_seconds - (monotonic() - self.started)
            reserve = min(90.0, self.request.timeout_seconds * 0.25)
            if self.omission_calls[source] >= omission_windows.MAX_CALLS or remaining <= reserve:
                self._finish_windows(
                    [window, *reversed(pending)], reason="Omission window budget exhausted."
                )
                return
            self.omission_calls[source] += 1
            excerpt = parent.text[window.start : window.end]
            if not excerpt.strip():
                self._finish_windows([window], reason=None)
                continue
            try:
                async with asyncio.timeout(remaining - reserve):
                    rows = await self._omit_window(batch=batch, window=window, excerpt=excerpt)
            except TruncatedResponseError:
                width = max(omission_windows.MIN_CHARS, len(excerpt) // 2)
                if width < len(excerpt) and not parent.is_table:
                    pending.extend(
                        reversed(
                            omission_windows.partition(text=parent.text, window=window, width=width)
                        )
                    )
                else:
                    self._finish_windows(
                        [window], reason="Provider truncated the smallest omission window."
                    )
                continue
            except (InferenceError, TimeoutError) as error:
                self._finish_windows(
                    [window, *reversed(pending)],
                    reason=_omission_failure(error),
                )
                return
            self._finish_windows([window], reason=None)
            for row in rows.claims:
                if (
                    omission_windows.covers(claim=row, text=excerpt)
                    and (claim := self.resolve(row, [window.citation])) is not None
                    and claim not in batch.candidates
                ):
                    batch.candidates.append(claim)

    async def _omit_window(
        self,
        *,
        batch: BatchResult,
        window: omission_windows.Window,
        excerpt: str,
    ) -> Claims:
        context: dict[str, object] = {
            "omission_window": window.model_dump(),
            "prior_claims": [
                (c.name, c.meaning, c.source, c.target)
                for c in batch.candidates
                if any(
                    a.citation == window.citation and normalized(a.quote) in normalized(excerpt)
                    for a in c.evidence
                )
            ],
        }
        if self.request.discovery_continuation:
            context["continuation_epoch"] = self.request.request_id
        if self.part(window.citation).is_table:
            context["column_headers"] = omission_windows.table_header(
                text=self.part(window.citation).text
            )
        return await self.call(
            stage=DiscoveryStage.COVERAGE,
            schema=Claims,
            indexes=[window.citation],
            prompt=self.request.instructions + "\n" + self._extraction_instructions(omissions=True),
            context=context,
            inputs=[InferenceInput(text=excerpt, evidence=self.part(window.citation).evidence)],
            output_tokens=(
                None if self._deferred_omissions_use_provider_limit else omission_windows.MAX_TOKENS
            ),
            use_provider_output_limit=self._deferred_omissions_use_provider_limit,
        )

    async def targeted_coverage(self, state: _State) -> _State:
        batches = state["batches"]
        known = self.approved | {
            claim.name for batch in batches for claim in batch.accepted if claim.kind == "concept"
        }
        recovered = await _complete_batches(
            self._recover_missing(batch=batch, number=i, known=known)
            for i, batch in enumerate(batches)
        )
        return {"batches": [*batches, *(b for b in recovered if b.candidates or b.findings)]}

    async def _recover_missing(
        self, *, batch: BatchResult, number: int, known: set[str]
    ) -> BatchResult:
        result = BatchResult(passages=batch.passages)
        edges = [claim for claim in batch.accepted if claim.kind == "relationship"]
        missing = {name for edge in edges for name in (edge.source, edge.target) if name} - known
        supported: dict[int, list[str]] = defaultdict(list)
        for edge in edges:
            for anchor in edge.evidence:
                supported[anchor.citation].append(normalized(anchor.quote))
        focus = self._recovery_focus(passages=batch.passages, supported=supported)
        orphans = [c for c in edges if c.source in missing or c.target in missing]
        prior = [*orphans, *(c for c in edges if c not in orphans)][:_RECOVERY_CONTEXT_LIMIT]
        targets = list(
            dict.fromkeys([(a.citation, a.quote) for c in orphans for a in c.evidence] + focus)
        )
        admitted = targets[: _RECOVERY_WINDOW_SIZE * _RECOVERY_WINDOW_LIMIT]
        pending = [
            admitted[i : i + _RECOVERY_WINDOW_SIZE]
            for i in range(0, len(admitted), _RECOVERY_WINDOW_SIZE)
        ]
        candidates = list(batch.candidates)
        for _ in range(_RECOVERY_CALL_LIMIT):
            if not pending:
                break
            window = pending.pop(0)
            try:
                added = await self._mine_recovery_window(
                    window=window, missing=missing, prior=prior
                )
            except TruncatedResponseError:
                if len(window) > 1:
                    split = len(window) // 2
                    pending[0:0] = [window[:split], window[split:]]
                else:
                    citation = window[0][0]
                    result.findings.append(
                        Finding(
                            stage="coverage",
                            batch=number,
                            detail=f"Recovery of passage {citation} reached its output limit.",
                        )
                    )
                continue
            for claim in added:
                if claim not in candidates:
                    result.candidates.append(claim)
                    candidates.append(claim)
        deferred = len(targets) - len(admitted) + sum(len(window) for window in pending)
        if deferred:
            result.findings.append(
                Finding(
                    stage="coverage",
                    batch=number,
                    detail=f"Deferred {deferred} focused excerpt(s) at the recovery budget.",
                )
            )
        return await self.check(result, number)

    async def _mine_recovery_window(
        self,
        *,
        window: Sequence[tuple[int, str]],
        missing: set[str],
        prior: Sequence[IdentifiedClaim],
    ) -> list[IdentifiedClaim]:
        indexes = list(dict.fromkeys(index for index, _ in window))
        snippets = [
            InferenceInput(
                text=_edge_context(
                    text=self.part(index).text, quotes=(q for i, q in window if i == index)
                ),
                evidence=self.part(index).evidence,
            )
            for index in indexes
        ]
        rows = await self.call(
            stage=DiscoveryStage.COVERAGE,
            schema=Claims,
            prompt=self.request.instructions + "\n" + _TARGETED_RECOVERY + EXTRACT,
            indexes=indexes,
            inputs=snippets,
            context={
                "missing_endpoint_names": sorted(missing),
                "focus_excerpts": [
                    {"citation": indexes.index(index) + 1, "quote": quote}
                    for index, quote in window
                ],
                "prior_claims": [c.model_dump(exclude={"claim_id", "evidence"}) for c in prior],
            },
        )
        return [claim for row in rows.claims if (claim := self.resolve(row, indexes)) is not None]

    def _recovery_focus(
        self, *, passages: Sequence[int], supported: Mapping[int, list[str]]
    ) -> list[tuple[int, str]]:
        uncovered: list[tuple[int, str]] = []
        qualified: list[tuple[int, str]] = []
        for index in passages:
            for part in _RECOVERY_SENTENCE.split(self.part(index).text):
                excerpt = normalized(part)
                if not excerpt:
                    continue
                if not any(q in excerpt or excerpt in q for q in supported.get(index, ())):
                    uncovered.append((index, excerpt))
                elif _RECOVERY_QUALIFIER.search(excerpt):
                    qualified.append((index, excerpt))
        return (uncovered + qualified)[:_RECOVERY_FOCUS_LIMIT]

    async def _recover_passage(self, *, batch: BatchResult, citation: int) -> None:
        parent = self.part(citation)
        window = self._window(citation)
        width = min(omission_windows.MAX_CHARS, max(omission_windows.MIN_CHARS, window.end // 2))
        windows = (
            omission_windows.table_windows(text=parent.text, window=window)
            if parent.is_table
            else omission_windows.partition(text=parent.text, window=window, width=width)
        )
        await self._process_windows(batch=batch, windows=windows)

    async def mine(self, batch: BatchResult, number: int, *, omissions: bool) -> BatchResult:
        result = batch.model_copy(deep=True)
        pending = [batch.passages]
        while pending:
            passages = pending.pop()
            frame = self._split_context(primary=passages, batch=batch.passages)
            try:
                rows = await self._mine_passages(
                    batch=batch, passages=frame, omissions=omissions, primary=passages
                )
            except TruncatedResponseError:
                if len(passages) == 1:
                    if omissions and self.config.resumable_omissions:
                        await self._recover_passage(batch=result, citation=passages[0])
                        continue
                    raise
                split = len(passages) // 2
                pending.extend((passages[split:], passages[:split]))
                result.findings.append(
                    Finding(
                        stage="coverage" if omissions else "extract",
                        batch=number,
                        detail="Split a truncated extraction at original passage boundaries.",
                    )
                )
                continue
            except (InferenceTimeoutError, TimeoutError):
                if not omissions or not self.config.resumable_omissions:
                    raise
                self._broad_omission_timed_out = True
                self._finish_windows(
                    (
                        self._window(i)
                        for i in chain(passages, chain.from_iterable(reversed(pending)))
                    ),
                    reason=_BROAD_OMISSION_TIMEOUT,
                )
                result.findings.append(
                    Finding(stage="coverage", batch=number, detail=_BROAD_OMISSION_TIMEOUT)
                )
                break
            if omissions and self.config.resumable_omissions:
                self._finish_windows((self._window(i) for i in passages), reason=None)
            self._retain_rows(
                result=result,
                rows=rows,
                passages=frame,
                number=number,
                primary=passages if frame != passages else None,
            )
        return result

    def _split_context(self, *, primary: list[int], batch: list[int]) -> list[int]:
        if not self.config.preserve_split_context or primary == batch:
            return primary
        first, last = primary[0], primary[-1]
        neighbors = {
            index
            for center, index in ((first, first - 1), (last, last + 1))
            if index in batch
            and self.part(index).evidence[0].source == self.part(center).evidence[0].source
        }
        return sorted(set(primary) | neighbors)

    def _retain_rows(
        self,
        *,
        result: BatchResult,
        rows: Claims | BoundClaims,
        passages: list[int],
        number: int,
        primary: list[int] | None = None,
    ) -> None:
        resolved = (
            self._bind(rows=rows, indexes=passages)
            if isinstance(rows, BoundClaims)
            else ((row.name, self.resolve(row, passages), None) for row in rows.claims)
        )
        for original, (name, claim, detail) in zip(rows.claims, resolved, strict=True):
            if primary is not None and not any(
                1 <= anchor.citation <= len(passages) and passages[anchor.citation - 1] in primary
                for anchor in original.evidence
            ):
                continue
            if claim is None:
                if self.stable_binding and isinstance(original, BoundDraft):
                    self._hold_unbound(batch=result, row=original, indexes=passages)
                result.findings.append(
                    Finding(
                        stage="lineage",
                        batch=number,
                        name=name,
                        detail="Check cited occurrences, participant IDs and qualifiers."
                        if self.config.binding_contract is not None
                        else "Check claim shape and exact supporting quotations.",
                    )
                )
            elif detail is not None and isinstance(claim, BoundClaim):
                result.held.append(claim)
                result.findings.append(
                    Finding(
                        stage="binding",
                        batch=number,
                        name=name,
                        claim_id=claim.claim_id,
                        detail=detail,
                    )
                )
            elif claim not in result.candidates:
                result.candidates.append(claim)

    def _hold_unbound(self, *, batch: BatchResult, row: BoundDraft, indexes: list[int]) -> None:
        if row.kind != "relationship":
            return
        anchors = [self.anchor(anchor=anchor, indexes=indexes) for anchor in row.evidence]
        evidence = [anchor for anchor in anchors if anchor is not None]
        identity = hash_json(
            value=record_value(
                value=(
                    self.request.scope,
                    row.name,
                    row.meaning,
                    tuple((self.part(a.citation).evidence[0], a.quote) for a in evidence),
                    tuple(self.part(i).evidence[0].id for i in indexes) if not evidence else (),
                )
            )
        ).value
        batch.unbound.append(UnboundRelationship(claim_id=identity, evidence=evidence))

    async def _mine_passages(
        self, *, batch: BatchResult, passages: list[int], omissions: bool, primary: list[int]
    ) -> Claims | BoundClaims:
        context: dict[str, object] = {}
        if omissions:
            existing = _Context.model_validate_json(self.request.context_json or "{}")
            known = {c.name for c in batch.candidates if c.kind == "concept"}
            known.update(c.name for c in existing.approved_meanings if c.kind == "concept")
            context["prior_claims"] = [
                evidence_binding.coverage_claim(c)
                if isinstance(c, BoundClaim)
                else (c.name, c.meaning, c.source, c.target)
                for c in batch.candidates
            ]
            context["unresolved_endpoint_names"] = sorted(
                {name for c in batch.candidates for name in (c.source, c.target) if name} - known
            )
            if self.config.mention_detector:
                context["mention_profile"] = self.config.mention_detector.profile
                context["mentions"] = [
                    {"citation": n, **hint.model_dump()}
                    for n, i in enumerate(passages, 1)
                    for hint in self.config.mention_detector(self.part(i).text)
                ]
        stage = DiscoveryStage.COVERAGE if omissions else DiscoveryStage.EXTRACT
        prompt = (
            self.request.instructions + "\n" + self._extraction_instructions(omissions=omissions)
        )
        if primary != passages:
            context["primary_passages"] = [
                i for i, passage in enumerate(passages, 1) if passage in primary
            ]
            prompt += (
                "\nOnly propose claims supported by at least one primary passage. "
                "Use the adjacent passages for identity and cross-sentence evidence."
            )
        if self.uses_mention_table:
            instructions = evidence_binding.MINING
            if self.stable_binding:
                instructions += endpoint_contract.MINING
            return await self.call(
                stage=stage,
                schema=BoundClaims,
                prompt=f"{prompt}\n{instructions}",
                indexes=passages,
                context=context,
            )
        return await self.call(
            stage=stage,
            schema=Claims,
            prompt=prompt,
            indexes=passages,
            context=context,
        )

    async def verify(self, state: _State) -> _State:
        return {
            "batches": await _complete_batches(
                self.check(batch, i) for i, batch in enumerate(state["batches"])
            )
        }

    def verification_passages(self, batch: BatchResult) -> list[int]:
        anchors = [
            a
            for claim in batch.candidates
            for qualified in (claim, *claim.conditions, *claim.exceptions)
            for a in qualified.evidence
        ]
        if not anchors:
            return list(batch.passages)
        indexes = list(dict.fromkeys(a.citation for a in anchors))
        references: dict[object, set[str]] = defaultdict(set)
        for anchor in anchors:
            revision = self.part(anchor.citation).evidence[0].source
            references[revision].update(cross_references(text=anchor.quote))
            if self.uses_mention_table:
                references[revision].update(evidence_binding.annex_references(anchor.quote))
        referenced = [
            i
            for i, part in enumerate(self.request.inputs, 1)
            if i not in indexes
            and (wanted := references.get(part.evidence[0].source))
            and any(
                line.strip().casefold().rstrip(".:") in wanted for line in part.text.splitlines()
            )
        ]
        located = {self.part(i).evidence[0].source for i in referenced}
        if self.uses_mention_table:
            referenced.extend(self._reference_continuations(indexes=indexes, referenced=referenced))
        candidates = [
            i
            for i in batch.passages
            if i not in indexes
            and i not in referenced
            and self.part(i).evidence[0].source in references
            and self.part(i).evidence[0].source not in located
        ]
        ranked = rank_passages(
            query=" ".join(c.meaning for c in batch.candidates),
            passages=[self.part(i).text for i in candidates],
            limit=_CONTEXT_PASSAGES,
        )
        remaining = self.config.batch_bytes - sum(len(self.part(i).text.encode()) for i in indexes)
        added = 0
        for i in [*referenced, *(candidates[pos] for pos in ranked)]:
            size = len(self.part(i).text.encode())
            if size <= remaining:
                indexes.append(i)
                remaining -= size
                added += 1
                if added == _CONTEXT_PASSAGES:
                    break
        return indexes

    def _reference_continuations(self, *, indexes: list[int], referenced: list[int]) -> list[int]:
        seen = {*indexes, *referenced}
        result: list[int] = []
        for index in referenced:
            evidence = self.part(index).evidence[0]
            locator = evidence.locator
            if isinstance(locator, DocumentSpan) and locator.page is not None:
                adjacent = self.pages.get((evidence.source, locator.page + 1))
                if adjacent is not None and adjacent not in seen:
                    result.append(adjacent)
                    seen.add(adjacent)
        return result

    async def check(self, batch: BatchResult, number: int, *, stage: str = "verify") -> BatchResult:
        if not batch.candidates:
            return batch
        result = batch.model_copy(deep=True)
        indexes = self.verification_passages(batch)
        claims = [_local_claim(claim, indexes) for claim in batch.candidates]
        size = _VERIFICATION_GROUP if self.config.verification == "fields" else len(claims)
        if self.config.targeted_recovery:
            size = min(size, _RECOVERY_VERIFICATION_GROUP)
        for start in range(0, len(claims), size):
            group = claims[start : start + size]
            assessments, protocol_findings = await self._grade_claims(
                group, indexes=indexes, stage=stage
            )
            result.findings.extend(protocol_findings)
            for candidate, assessment in zip(
                result.candidates[start : start + size], assessments, strict=True
            ):
                result.assessments.append(assessment)
                if assessment.status == "supported":
                    result.accepted.append(candidate)
                else:
                    result.findings.append(
                        Finding(
                            stage="semantic",
                            batch=number,
                            name=candidate.name,
                            claim_id=candidate.claim_id,
                            detail=assessment.detail,
                        )
                    )
        return result

    async def _grade_claims(
        self,
        claims: list[IdentifiedClaim],
        *,
        indexes: list[int],
        stage: str,
        retry_unattributed: bool = True,
    ) -> tuple[list[Assessment], list[Finding]]:
        try:
            assessments, findings = await self.grade(
                claims,
                indexes=indexes,
                stage=stage,
                context={"claims": [self._frame(c, index=i) for i, c in enumerate(claims)]},
            )
        except TruncatedResponseError:
            if len(claims) == 1:
                raise
            reason = "Split a truncated verifier batch and rechecked every claim."
        else:
            if not (
                retry_unattributed
                and self.config.verification == "aggregate"
                and len(claims) > 1
                and all(a.status == "invalid" for a in assessments)
            ):
                return assessments, findings
            reason = "Split a verifier batch with no attributable verdicts for one bounded retry."
            retry_unattributed = False
        split = len(claims) // 2
        left, left_findings = await self._grade_claims(
            claims[:split], indexes=indexes, stage=stage, retry_unattributed=retry_unattributed
        )
        right, right_findings = await self._grade_claims(
            claims[split:], indexes=indexes, stage=stage, retry_unattributed=retry_unattributed
        )
        return [*left, *right], [
            Finding(stage=stage, detail=reason),
            *left_findings,
            *right_findings,
        ]

    def _frame(self, claim: IdentifiedClaim, *, index: int | None = None) -> dict[str, object]:
        framed = claim.model_dump(
            exclude={"claim_id"} if self.config.verification == "aggregate" else set()
        )

        if self.config.verification == "aggregate" and index is not None:
            framed["index"] = index
        return framed

    async def grade(
        self,
        claims: list[IdentifiedClaim],
        *,
        indexes: list[int],
        stage: str,
        context: dict[str, object],
        endpoints: _EndpointReview | None = None,
    ) -> tuple[list[Assessment], list[Finding]]:
        snippets = endpoints.snippets if endpoints else None
        endpoint_instruction = endpoints.instruction if endpoints else ""
        inference_stage = DiscoveryStage.VERIFY if endpoints is None else DiscoveryStage.ENDPOINTS
        if endpoints is not None and self.stable_binding:
            return await self._grade_stable_endpoints(
                claims=claims, indexes=indexes, context=context, review=endpoints
            )
        if self.config.verification == "aggregate":
            prompt = (
                aggregate_verification.CHECK_EDGES + endpoint_instruction
                if snippets is not None
                else aggregate_verification.VERIFY
            )
            grades = await self.call(
                stage=inference_stage,
                schema=aggregate_verification.Verdicts,
                prompt=prompt + (evidence_binding.CHECK if self.uses_mention_table else ""),
                indexes=indexes,
                inputs=snippets,
                context=context,
            )
            return [
                aggregate_verification.assessment(
                    claim=c, votes=grades.verdicts, index=i, stage=stage
                )
                for i, c in enumerate(claims)
            ], []
        votes = await self.call(
            stage=inference_stage,
            schema=Verdicts,
            prompt=CHECK_EDGES + endpoint_instruction if snippets is not None else VERIFY,
            indexes=indexes,
            inputs=snippets,
            context=context,
        )
        findings: list[Finding] = []
        expected = {c.claim_id for c in claims}
        if any(v.claim_id not in expected for v in votes.verdicts):
            findings.append(Finding(stage="protocol", detail="Unknown verdict ID."))
        resolve: Callable[[Anchor], Anchor | None] = (
            (lambda anchor: self.anchor(anchor=anchor, indexes=indexes))
            if snippets is None
            else partial(self._snippet_anchor, indexes=indexes, inputs=snippets)
        )
        return [
            assess(claim=c, votes=votes.verdicts, stage=stage, resolve=resolve) for c in claims
        ], findings

    def _binding_key(self, *, claim: IdentifiedClaim) -> str:
        if not isinstance(claim, BoundClaim) or claim.subject is None or claim.object is None:
            raise InferenceError(message="Use a directed claim with two exact participants.")
        return hash_json(
            value=(
                endpoint_contract.VERSION,
                claim.claim_id,
                self.approved_keys.get(claim.source or "", claim.source),
                self.approved_keys.get(claim.target or "", claim.target),
                claim.subject.id,
                claim.object.id,
                claim.meaning,
                claim.modality,
                evidence_binding.qualifier_paths(claim.qualifiers),
            )
        ).value

    async def _grade_stable_endpoints(
        self,
        *,
        claims: list[IdentifiedClaim],
        indexes: list[int],
        context: dict[str, object],
        review: _EndpointReview,
    ) -> tuple[list[Assessment], list[Finding]]:
        result = await self.call(
            stage=DiscoveryStage.ENDPOINTS,
            schema=endpoint_contract.EndpointVerdicts,
            prompt=aggregate_verification.CHECK_EDGES
            + review.instruction
            + evidence_binding.CHECK
            + endpoint_contract.VERIFY_ENDPOINTS,
            indexes=indexes,
            inputs=review.snippets,
            context=context,
        )
        by_claim: dict[str, list[endpoint_contract.EndpointVerdict]] = defaultdict(list)
        for verdict in result.verdicts:
            by_claim[verdict.claim_id].append(verdict)
        expected = {claim.claim_id for claim in claims}
        findings = (
            [Finding(stage="protocol", detail="Unknown endpoint verdict claim ID.")]
            if by_claim.keys() - expected
            else []
        )
        return [
            self._assess_stable_endpoint(
                claim=claim,
                votes=by_claim[claim.claim_id],
                indexes=indexes,
                snippets=review.snippets,
            )
            for claim in claims
        ], findings

    def _assess_stable_endpoint(
        self,
        *,
        claim: IdentifiedClaim,
        votes: Sequence[endpoint_contract.EndpointVerdict],
        indexes: list[int],
        snippets: list[InferenceInput],
    ) -> Assessment:
        assessment = Assessment(
            stage="endpoints",
            claim_id=claim.claim_id,
            meaning=claim.meaning,
            verdict=None,
            status="invalid",
            detail="The endpoint verdict is missing, duplicated, or identifies an earlier binding.",
        )
        if len(votes) != 1 or votes[0].binding_key != self._binding_key(claim=claim):
            return assessment
        vote = votes[0]
        if vote.status != "supported":
            assessment.status = vote.status
            assessment.detail = "The directed endpoint check did not support this relationship."
            return assessment
        resolved = [self._snippet_anchor(anchor, indexes, snippets) for anchor in vote.evidence]
        evidence = [anchor for anchor in resolved if anchor is not None]
        if (
            len(evidence) != len(resolved)
            or not isinstance(claim, BoundClaim)
            or not self._supports_participants(claim=claim, evidence=evidence)
        ):
            assessment.detail = (
                "The verdict did not cite exact evidence for both bound participants."
            )
            return assessment
        self.endpoint_evidence[claim.claim_id] = evidence
        assessment.status = "supported"
        assessment.detail = "The cited source supports the verified directed binding."
        return assessment

    async def repair(self, state: _State) -> _State:
        return {
            "batches": await _complete_batches(
                self.repair_batch(batch, i) for i, batch in enumerate(state["batches"])
            )
        }

    async def repair_batch(self, batch: BatchResult, number: int) -> BatchResult:
        disputed = {f.claim_id: f.detail for f in batch.findings if f.stage == "semantic"}
        originals = {c.claim_id: c for c in batch.candidates if c.claim_id in disputed}
        if not originals:
            return batch
        result = batch.model_copy(deep=True)
        repairs = await self._repairs(result, originals, disputed)
        if not repairs:
            return result
        checked = await self.check(
            BatchResult(passages=batch.passages, candidates=repairs), number, stage="repair"
        )
        result.candidates.extend(repairs)
        result.accepted.extend(checked.accepted)
        result.findings.extend(checked.findings)
        result.assessments.extend(checked.assessments)
        return result

    async def _repairs(
        self,
        batch: BatchResult,
        originals: dict[str, IdentifiedClaim],
        disputed: dict[str | None, str],
    ) -> list[IdentifiedClaim]:
        # Candidate citations use the global inventory. Frame every anchor for this request.
        indexes = list(
            dict.fromkeys(
                [
                    *(
                        self.verification_passages(batch)
                        if self.uses_mention_table
                        else batch.passages
                    ),
                    *(
                        a.citation
                        for c in originals.values()
                        for q in (c, *c.conditions, *c.exceptions)
                        for a in q.evidence
                    ),
                ]
            )
        )
        local_claims = [_local_claim(claim, indexes) for claim in originals.values()]
        repairs: list[IdentifiedClaim] = []
        for start in range(0, len(local_claims), _VERIFICATION_GROUP):
            group = local_claims[start : start + _VERIFICATION_GROUP]
            context: dict[str, object] = {
                "disputed_claims": [
                    {"claim": c.model_dump(), "finding": disputed[c.claim_id]} for c in group
                ]
            }
            if self.uses_mention_table:
                instructions = evidence_binding.MINING
                if self.stable_binding:
                    instructions += endpoint_contract.MINING
                rows_bound = await self.call(
                    stage=DiscoveryStage.REPAIR,
                    schema=BoundRepairs,
                    prompt=REPAIR
                    + EXTRACT
                    + instructions
                    + " Copy the disputed claim_id for each replacement.",
                    indexes=indexes,
                    context=context,
                )
                counts = Counter(row.claim_id for row in rows_bound.claims)
                requested = {row.claim_id: row for row in group}
                for row, (_, bound, detail) in zip(
                    rows_bound.claims, self._bind(rows=rows_bound, indexes=indexes), strict=True
                ):
                    prior = requested.get(row.claim_id)
                    if (
                        bound is None
                        or detail is not None
                        or prior is None
                        or counts[row.claim_id] != 1
                        or (bound.kind, bound.name) != (prior.kind, prior.name)
                    ):
                        batch.findings.append(
                            Finding(
                                stage="repair",
                                claim_id=row.claim_id if prior is not None else None,
                                detail="Unattributable repair or unresolved source occurrence.",
                            )
                        )
                    else:
                        repairs.append(bound)
                continue
            rows = await self.call(
                stage=DiscoveryStage.REPAIR,
                schema=Repairs,
                prompt=REPAIR + EXTRACT,
                indexes=indexes,
                context=context,
            )
            for original in group:
                matches = [row for row in rows.claims if row.claim_id == original.claim_id]
                if len(matches) == 1 and (matches[0].kind, matches[0].name) == (
                    original.kind,
                    original.name,
                ):
                    resolved = self.resolve(matches[0], indexes)
                    if resolved is not None:
                        repairs.append(resolved)
        return repairs

    async def reconcile(self, state: _State) -> _State:
        candidates = [c for b in state["batches"] for c in b.accepted if c.kind == "concept"]
        ambiguous = ambiguous_concept_names(occurrences=candidates)
        concepts = {c.name: c for c in candidates if c.name not in ambiguous}
        if self.alias_index is not None:
            self.aliases.update(
                self.alias_index.aliases(
                    claims=list(concepts.values()), asserted_only=bool(self.source_identity_policy)
                )
            )
            return state
        checked: set[frozenset[str]] = set()
        for rows in _alias_groups(concepts):
            inputs = [
                InferenceInput(
                    text=c.evidence[0].quote,
                    evidence=self.part(c.evidence[0].citation).evidence,
                )
                for c in rows
            ]
            result = await self.call(
                stage=DiscoveryStage.RECONCILE,
                schema=Aliases,
                prompt=RECONCILE,
                indexes=[],
                inputs=inputs,
                context={
                    "concepts": [
                        {
                            "name": c.name,
                            "meaning": c.meaning,
                            "quote": c.evidence[0].quote,
                            **(
                                {"title": c.title, "role": c.mention.role if c.mention else None}
                                if isinstance(c, BoundClaim)
                                else {}
                            ),
                        }
                        for c in rows
                    ]
                },
            )
            visible = {c.name: c for c in rows}
            for alias in result.aliases:
                if not self.valid_alias(alias, visible):
                    continue
                pair = frozenset((alias.alternate, alias.preferred))
                if pair in checked:
                    continue
                checked.add(pair)
                witness = await self._alias_identity_witness(
                    alternate=visible[alias.alternate], preferred=visible[alias.preferred]
                )
                if witness is None:
                    state["batches"][0].findings.append(
                        Finding(
                            stage="reconcile",
                            name=alias.alternate,
                            detail=(
                                f"Review identity with {alias.preferred}. "
                                "No explicit source witness."
                            ),
                        )
                    )
                    continue
                self.aliases[alias.alternate] = VerifiedAlias(
                    alternate=alias.alternate,
                    preferred=alias.preferred,
                    alternate_quote=alias.alternate_quote,
                    preferred_quote=alias.preferred_quote,
                    reason=alias.reason,
                    identity_witness=witness,
                )
        return state

    async def _alias_identity_witness(self, *, alternate: Claim, preferred: Claim) -> Anchor | None:
        anchors = [alternate.evidence[0], preferred.evidence[0]]
        indexes = list(dict.fromkeys(a.citation for a in anchors))
        snippets = [
            InferenceInput(
                text=_edge_context(
                    text=self.part(index).text,
                    quotes=(a.quote for a in anchors if a.citation == index),
                ),
                evidence=self.part(index).evidence,
            )
            for index in indexes
        ]
        first, second = _designations(claim=alternate), _designations(claim=preferred)
        if self.stable_binding and not any(
            clause
            for snippet in snippets
            for clause in evidence_binding.identity_clauses(
                quote=snippet.text, first=first, second=second
            )
        ):
            return None
        try:
            result = await self.call(
                stage=DiscoveryStage.ALIAS_PROOF,
                schema=AliasIdentityWitness,
                prompt=VERIFY_ALIAS_IDENTITY,
                indexes=indexes,
                inputs=snippets,
                context={
                    "designations": [
                        {"name": c.name, "title": c.title} for c in (alternate, preferred)
                    ]
                },
            )
        except (_StageFrameLimitError, TruncatedResponseError):
            return None
        if result.identity_witness is None:
            return None
        witness = self._snippet_anchor(result.identity_witness, indexes, snippets)
        if witness is None:
            return None
        supported = (
            any(evidence_binding.identity_clauses(quote=witness.quote, first=first, second=second))
            if self.stable_binding
            else _distinct_designations(first=alternate, second=preferred, quote=witness.quote)
        )
        return witness if supported else None

    def valid_alias(self, alias: Alias, visible: dict[str, Claim]) -> bool:
        old, new = visible.get(alias.alternate), visible.get(alias.preferred)
        if (
            old is None
            or new is None
            or old.name == new.name
            or old.name in self.aliases
            or new.name in self.aliases
        ):
            return False
        if any(a.preferred == old.name for a in self.aliases.values()):
            return False
        return (
            old.conditions == new.conditions
            and old.exceptions == new.exceptions
            and old.evidence[0].quote == alias.alternate_quote
            and new.evidence[0].quote == alias.preferred_quote
        )

    async def check_edges(self, state: _State) -> _State:
        graph = self._assemble(state["batches"])
        rows = graph.claims
        context = _Context.model_validate_json(self.request.context_json or "{}")
        meanings = {item.name: item.meaning for item in context.approved_meanings}
        meanings.update({name: value[1] for name, value in self.pending_concepts.items()})
        meanings.update({c.name: c.meaning for c in rows if c.kind == "concept"})
        originals = {c.claim_id: c for b in state["batches"] for c in b.accepted}
        original_meanings = {c.name: c.meaning for c in originals.values() if c.kind == "concept"}
        edges = [c for c in rows if c.kind == "relationship"]
        if self.decisions_gate is not None:
            bypassed = await self._classify_edges(graph=graph, batches=state["batches"])
            edges = [edge for edge in edges if edge.claim_id not in bypassed]
        size = _VERIFICATION_GROUP if self.config.verification == "fields" else 8
        groups = _endpoint_groups(
            edges, originals=originals, size=size, fields=self.config.verification == "fields"
        )
        for wave in batched(groups, self.config.endpoint_concurrency, strict=False):
            decisions = await _complete_batches(
                self._check_edge_group(
                    collapsed=collapsed,
                    group=group,
                    originals=originals,
                    meanings=meanings,
                    original_meanings=original_meanings,
                )
                for collapsed, group in wave
            )
            for (_, group), (assessments, protocol_findings) in zip(wave, decisions, strict=True):
                state["batches"][0].findings.extend(protocol_findings)
                for c, assessment in zip(group, assessments, strict=True):
                    owner = next(
                        batch
                        for batch in state["batches"]
                        if any(row.claim_id == c.claim_id for row in batch.accepted)
                    )
                    owner.assessments.append(assessment)
                    if assessment.status != "supported":
                        self.edge_findings[c.claim_id] = Finding(
                            stage="endpoints",
                            name=c.name,
                            claim_id=c.claim_id,
                            detail=assessment.detail,
                        )
        return state

    async def _classify_edges(self, *, graph: ClaimGraph, batches: list[BatchResult]) -> set[str]:
        gate = self.decisions_gate
        if gate is None:
            return set()
        alias_names = set(self.aliases) | {alias.preferred for alias in self.aliases.values()}
        alias_names.update(
            normalized(alias).casefold().replace(" ", "-")
            for _, alternatives in self.request.approved_concept_aliases
            for alias in alternatives
        )
        audit, candidates = endpoint_decisions.plan(
            graph=graph,
            batches=batches,
            inputs=self.request.inputs,
            blocked_names=alias_names | self.approved | self.pending_concepts.keys(),
        )
        bypassed = await gate.route(
            request=self.request, audit=audit, candidates=candidates, started=self.started
        )
        self.decisions_audit = audit
        for receipt in audit.calls:
            if receipt.input_tokens is not None or receipt.output_tokens is not None:
                self.receipts.append(
                    Receipt(
                        model_id=endpoint_decisions.MODEL,
                        provider_endpoint=openai_decisions.URL,
                        input_tokens=receipt.input_tokens,
                        output_tokens=receipt.output_tokens,
                        stage="endpoint-decisions",
                        profile=openai_decisions.PROFILE,
                    )
                )
        for batch in batches:
            batch.assessments.extend(
                Assessment(
                    stage="endpoints",
                    claim_id=claim.claim_id,
                    meaning=claim.meaning,
                    verdict=None,
                    status="supported",
                    detail="Decisions supported the exact directed claim.",
                )
                for claim in batch.accepted
                if claim.claim_id in bypassed
            )
        return bypassed

    async def _check_edge_group(
        self,
        *,
        collapsed: bool,
        group: list[IdentifiedClaim],
        originals: Mapping[str, IdentifiedClaim],
        meanings: Mapping[str, str],
        original_meanings: Mapping[str, str],
    ) -> tuple[list[Assessment], list[Finding]]:
        evidence = [a for c in group for q in (c, *c.conditions, *c.exceptions) for a in q.evidence]
        indexes = list(dict.fromkeys(a.citation for a in evidence))
        snippets = [
            InferenceInput(
                text=_edge_context(
                    text=self.part(i).text,
                    quotes=dict.fromkeys(a.quote for a in evidence if a.citation == i),
                ),
                evidence=self.part(i).evidence,
            )
            for i in indexes
        ]
        inspect: list[dict[str, object]] = []
        for index, claim in enumerate(group):
            original = originals[claim.claim_id]
            frame = self._frame(_local_claim(claim, indexes), index=index)
            packet = _endpoint_packet(
                claim=claim,
                original=original,
                frame=frame,
                meanings=meanings,
                original_meanings=original_meanings,
            )
            if self.stable_binding:
                frame["claim_id"] = claim.claim_id
                packet["binding_key"] = self._binding_key(claim=claim)
            inspect.append(packet)
        instruction = (
            ALIGNED_ENDPOINTS
            if any("source_wording_before_reconciliation" in p for p in inspect)
            else ""
        )
        if collapsed:
            instruction += COLLAPSED_ENDPOINTS
        assessments, protocol_findings = await self.grade(
            group,
            stage="endpoints",
            indexes=indexes,
            endpoints=_EndpointReview(snippets=snippets, instruction=instruction),
            context={"edges": inspect},
        )
        if self.config.verification == "aggregate":
            pending = {
                i: (frame, originals[claim.claim_id])
                for i, (claim, frame, assessment) in enumerate(
                    zip(group, inspect, assessments, strict=True)
                )
                if assessment.status == "supported"
                and claim.source == claim.target
                and originals[claim.claim_id].source != originals[claim.claim_id].target
            }
            await self._confirm_self_actions(
                pending=pending, assessments=assessments, indexes=indexes, snippets=snippets
            )
        return assessments, protocol_findings

    async def recover_held_endpoints(self, state: _State) -> _State:
        """Append an independently verified overlay to the completed baseline graph."""
        graph = self._assemble(state["batches"])
        held = held_endpoints.assembly_holds(graph=graph, batches=state["batches"])
        ordered = sorted(
            held.values(),
            key=lambda item: (min(a.citation for a in item.claim.evidence), item.claim.claim_id),
        )
        admitted = ordered[: held_endpoints.LIMIT]
        for item in ordered[held_endpoints.LIMIT :]:
            item.reason = "Deferred at the held endpoint recovery limit. " + item.reason
        self.held_recovery = held_endpoints.Recovery(held=ordered)
        if not admitted:
            return state
        remaining = self.request.timeout_seconds - (monotonic() - self.started) - 0.5
        try:
            async with asyncio.timeout(min(180.0, remaining)):
                repair_input = (
                    [
                        item.model_copy(
                            update={
                                "claim": held_endpoints.expand_evidence(
                                    claim=item.claim, inputs=self.request.inputs
                                )
                            }
                        )
                        for item in admitted
                    ]
                    if self.config.resumable_omissions
                    else admitted
                )
                repaired = await self._repair_held(graph=graph, held=repair_input)
        except (InferenceError, TimeoutError):
            for item in admitted:
                item.reason = "Held endpoint recovery could not be completed. " + item.reason
            return state
        recovered = held_endpoints.admit(graph=graph, repaired=repaired)
        if recovered and not self._fits_held_overlay(graph=graph, recovered=recovered):
            for item in admitted:
                item.reason = "Deferred at the discovery output byte budget. " + item.reason
            return state
        resolved = {item.edge.claim_id for item in recovered}
        self.held_recovery = held_endpoints.Recovery(
            recovered=recovered,
            held=[item for item in ordered if item.claim.claim_id not in resolved],
        )
        return state

    def _fits_held_overlay(
        self, *, graph: ClaimGraph, recovered: list[held_endpoints.RecoveredEdge]
    ) -> bool:
        limit = self.request.discovery_output_bytes
        if limit is None:
            return True
        rows = [claim for claim in graph.claims if claim.claim_id not in self.edge_findings]
        names = proposal_names(claims=rows)
        held_endpoints.append_overlay(
            recovery=held_endpoints.Recovery(recovered=recovered),
            rows=rows,
            names=names,
            origins={},
        )
        return len(json.dumps(_sdk_rows(rows, names=names)).encode()) <= limit

    async def _repair_held(
        self, *, graph: ClaimGraph, held: list[held_endpoints.HeldClaim]
    ) -> list[held_endpoints.RecoveredEdge]:
        context = _Context.model_validate_json(self.request.context_json or "{}")
        aliases = dict(self.request.approved_concept_aliases)
        inventory = held_endpoints.candidates(
            graph=graph,
            approved=[
                (item.name, self.approved_keys[item.name], item.meaning, aliases.get(item.name, ()))
                for item in context.approved_meanings
                if item.name in self.approved_keys
            ],
            aliases={
                old: alias.preferred
                for old, alias in self.aliases.items()
                if isinstance(alias, VerifiedAlias)
            },
        )
        records = held_endpoints.resolve(
            held=held, choices=(), inventory=inventory, inputs=self.request.inputs
        )
        if unresolved := [item for item in held if item.claim.claim_id not in records]:
            inputs, indexes = self._held_snippets(claims=[item.claim for item in unresolved])
            choices = await self.call(
                stage=DiscoveryStage.HELD_REPAIR,
                schema=held_endpoints.RepairChoices,
                prompt=held_endpoints.PROMPT,
                indexes=indexes,
                inputs=inputs,
                context={
                    "held_claims": [
                        self._frame(_local_claim(item.claim, indexes), index=i)
                        for i, item in enumerate(unresolved)
                    ],
                    "candidates": [
                        c.packet()
                        for c in held_endpoints.relevant(held=unresolved, inventory=inventory)
                    ],
                },
            )
            records.update(
                held_endpoints.resolve(
                    held=unresolved,
                    choices=choices.choices,
                    inventory=inventory,
                    inputs=self.request.inputs,
                )
            )
        return await self._verify_held(
            records=list(records.values()),
            originals={item.claim.claim_id: item.claim for item in held},
        )

    def _held_snippets(
        self, *, claims: Sequence[IdentifiedClaim]
    ) -> tuple[list[InferenceInput], list[int]]:
        evidence = [
            a
            for claim in claims
            for q in (claim, *claim.conditions, *claim.exceptions)
            for a in q.evidence
        ]
        indexes = list(dict.fromkeys(a.citation for a in evidence))
        return (
            [
                InferenceInput(
                    text=self._held_excerpt(
                        index=i,
                        quotes=dict.fromkeys(a.quote for a in evidence if a.citation == i),
                    ),
                    evidence=self.part(i).evidence,
                )
                for i in indexes
            ],
            indexes,
        )

    def _held_excerpt(self, *, index: int, quotes: Iterable[str]) -> str:
        part = self.part(index)
        if self.config.resumable_omissions and part.is_table:
            return "\n[…]\n".join((omission_windows.table_header(text=part.text), *quotes))
        return _edge_context(text=part.text, quotes=quotes)

    async def _verify_held(
        self,
        *,
        records: list[held_endpoints.RecoveredEdge],
        originals: Mapping[str, IdentifiedClaim],
    ) -> list[held_endpoints.RecoveredEdge]:
        if not records:
            return []
        inputs, indexes = self._held_snippets(claims=[item.edge for item in records])
        votes = await self.call(
            stage=DiscoveryStage.HELD_VERIFY,
            schema=aggregate_verification.Verdicts,
            prompt=aggregate_verification.CHECK_EDGES + ALIGNED_ENDPOINTS,
            indexes=indexes,
            inputs=inputs,
            context={
                "edges": [
                    _endpoint_packet(
                        claim=item.edge,
                        original=originals[item.edge.claim_id],
                        frame=self._frame(_local_claim(item.edge, indexes), index=i),
                        meanings={
                            item.edge.source or "": item.source_meaning,
                            item.edge.target or "": item.target_meaning,
                        },
                        original_meanings={},
                    )
                    for i, item in enumerate(records)
                ]
            },
        )
        return [
            item
            for i, item in enumerate(records)
            if aggregate_verification.assessment(
                claim=item.edge, votes=votes.verdicts, index=i, stage="held_verify"
            ).status
            == "supported"
        ]

    async def recover_focused_omissions(self, state: _State) -> _State:
        """Collect verified additions without feeding them back through baseline assembly."""
        graph, rows, _ = self._checked_graph(batches=state["batches"])
        names = proposal_names(claims=rows)
        held_endpoints.append_overlay(
            recovery=self.held_recovery, rows=rows, names=names, origins=graph.origins
        )
        grouped: dict[SourceRevision, list[int]] = defaultdict(list)
        for index, part in enumerate(self.request.inputs, start=1):
            grouped[part.evidence[0].source].append(index)
        for indexes in grouped.values():
            follow_up = focused_omissions.FollowUp(
                excerpts=focused_omissions.select(
                    inputs=self.request.inputs, indexes=indexes, baseline=rows
                )
            )
            self.focused_omissions.append(follow_up)
            if follow_up.excerpts:
                await self._focused_source(follow_up=follow_up, rows=rows, names=names)
        return state

    async def _focused_source(
        self,
        *,
        follow_up: focused_omissions.FollowUp,
        rows: list[IdentifiedClaim],
        names: dict[str, str],
    ) -> None:
        remaining = self.request.timeout_seconds - (monotonic() - self.started) - 1.0
        try:
            async with asyncio.timeout(min(focused_omissions.TIMEOUT_SECONDS, remaining)):
                additions = await self._focused_claims(follow_up=follow_up, rows=rows, names=names)
        except TruncatedResponseError:
            follow_up.reason = "The focused provider response reached its output limit."
            return
        except TimeoutError:
            follow_up.reason = "The focused recovery deadline expired."
            return
        except InferenceError as error:
            follow_up.reason = (
                error.issue.message
                if error.issue is not None
                else "Focused inference or response validation failed."
            )
            return
        all_rows = list(rows)
        all_names = dict(names)
        focused_omissions.append(rows=all_rows, names=all_names, origins={}, additions=additions)
        limit = self.request.discovery_output_bytes
        if (
            limit is not None
            and len(json.dumps(_sdk_rows(all_rows, names=all_names)).encode()) > limit
        ):
            follow_up.reason = "Focused additions exceed the SDK graph byte limit."
            return
        follow_up.additions = all_rows[len(rows) :]
        rows[:] = all_rows
        names.update(all_names)

    async def _focused_claims(
        self,
        *,
        follow_up: focused_omissions.FollowUp,
        rows: Sequence[IdentifiedClaim],
        names: Mapping[str, str],
    ) -> list[IdentifiedClaim]:
        windows = follow_up.excerpts
        indexes = [window.citation for window in windows]
        excerpts = [self.part(w.citation).text[w.start : w.end] for w in windows]
        inputs = [
            InferenceInput(text=excerpt, evidence=self.part(index).evidence)
            for excerpt, index in zip(excerpts, indexes, strict=True)
        ]
        prior = focused_omissions.relevant(rows=rows, names=names, excerpts=excerpts)
        result = await self.call(
            stage=DiscoveryStage.FOCUSED_OMISSIONS,
            schema=Claims,
            prompt=self.request.instructions + "\n" + focused_omissions.EXTRACT,
            indexes=indexes,
            inputs=inputs,
            context={
                "focused_phase": "extract",
                "excerpts": [w.model_dump() for w in windows],
                "existing_assertions": prior,
            },
            output_tokens=focused_omissions.MAX_TOKENS,
        )
        claims: list[tuple[Claim, IdentifiedClaim]] = []
        inventory = list(range(1, len(self.request.inputs) + 1))
        for local in result.claims[: focused_omissions.MAX_CLAIMS]:
            exact = focused_omissions.reanchor(claim=local, windows=windows, evidence=excerpts)
            if (
                exact is not None
                and (claim := self.resolve(exact, inventory)) is not None
                and all(
                    a.quote in self.part(a.citation).text
                    for piece in (claim, *claim.conditions, *claim.exceptions)
                    for a in piece.evidence
                )
            ):
                claims.append((local, claim))
        follow_up.proposed = [claim for _, claim in claims]
        verified = await self._focused_review(
            claims=claims, inputs=inputs, indexes=indexes, prior=prior, endpoints=False
        )
        follow_up.verified = [claim for _, claim in verified]
        admitted = focused_omissions.admit(
            baseline=rows,
            names=names,
            verified=follow_up.verified,
            reserved=set(names.values()) | self.approved,
        )
        admitted_ids = {c.claim_id for c in admitted}
        directed = await self._focused_review(
            claims=[
                p for p in verified if p[1].kind == "relationship" and p[1].claim_id in admitted_ids
            ],
            inputs=inputs,
            indexes=indexes,
            prior=prior,
            endpoints=True,
            definitions=[c for c in admitted if c.kind == "concept"],
        )
        passed = {claim.claim_id for _, claim in directed}
        return [c for c in admitted if c.kind == "concept" or c.claim_id in passed]

    async def _focused_review(  # noqa: PLR0913 - Explicit source frames and review phase.
        self,
        *,
        claims: list[tuple[Claim, IdentifiedClaim]],
        inputs: list[InferenceInput],
        indexes: list[int],
        prior: list[dict[str, object]],
        endpoints: bool,
        definitions: Sequence[IdentifiedClaim] = (),
    ) -> list[tuple[Claim, IdentifiedClaim]]:
        if not claims:
            return []
        phase = "endpoints" if endpoints else "verify"
        votes = await self.call(
            stage=DiscoveryStage.FOCUSED_OMISSIONS,
            schema=aggregate_verification.Verdicts,
            prompt=focused_omissions.ENDPOINTS if endpoints else focused_omissions.VERIFY,
            indexes=indexes,
            inputs=inputs,
            context={
                "focused_phase": phase,
                "edges" if endpoints else "claims": [
                    {"index": i, **claim.model_dump()} for i, (claim, _) in enumerate(claims)
                ],
                "existing_assertions": prior,
                "new_concepts": [
                    {"name": c.name, "title": c.title, "meaning": c.meaning} for c in definitions
                ],
            },
            output_tokens=focused_omissions.MAX_TOKENS,
        )
        if sorted(vote.index for vote in votes.verdicts) != list(range(len(claims))):
            raise InferenceError(
                message="The focused verifier did not return one verdict per claim."
            )
        supported = {vote.index for vote in votes.verdicts if vote.status == "supported"}
        return [claim for index, claim in enumerate(claims) if index in supported]

    async def _confirm_self_actions(
        self,
        *,
        pending: dict[int, tuple[dict[str, object], IdentifiedClaim]],
        assessments: list[Assessment],
        indexes: list[int],
        snippets: list[InferenceInput],
    ) -> None:
        if not pending:
            return
        response = await self.call(
            stage=DiscoveryStage.SELF_ACTION,
            schema=ActionConfirmations,
            prompt=CONFIRM_SELF_ACTION,
            indexes=indexes,
            inputs=snippets,
            context={"edges": [{"index": i, **frame} for i, (frame, _) in pending.items()]},
        )
        for i, (_, original) in pending.items():
            rows = [p.action for p in response.confirmations if p.index == i]
            action = (
                self._snippet_anchor(rows[0], indexes, snippets)
                if len(rows) == 1 and rows[0]
                else None
            )
            if action is not None and any(
                a.citation == action.citation and normalized(action.quote) in normalized(a.quote)
                for a in original.evidence
            ):
                if self.stable_binding and action not in self.endpoint_evidence[original.claim_id]:
                    self.endpoint_evidence[original.claim_id].append(action)
                continue
            assessments[i].status = "insufficient"
            assessments[i].detail = (
                "Review whether the source establishes the claimed action on the same participant "
                "in addition to identifying their two designations."
            )

    def _snippet_anchor(
        self, anchor: Anchor, indexes: list[int], inputs: list[InferenceInput]
    ) -> Anchor | None:
        if not 1 <= anchor.citation <= len(inputs) or normalized(anchor.quote) not in normalized(
            inputs[anchor.citation - 1].text
        ):
            return None
        resolved = self.anchor(anchor=anchor, indexes=indexes)
        if resolved is None or not self.stable_binding:
            return resolved
        quote = evidence_binding.exact_quote(
            text=self.part(resolved.citation).text,
            quote=resolved.quote,
        )
        return Anchor(citation=resolved.citation, quote=quote) if quote is not None else None

    def _assemble(self, batches: list[BatchResult]) -> ClaimGraph:
        return assemble_claims(
            accepted=(c for batch in batches for c in batch.accepted),
            aliases=self.aliases,
            approved_concepts=self.approved | self.pending_concepts.keys(),
            consolidate_punctuation=self.config.targeted_recovery,
        )

    def finish(self, *, batches: list[BatchResult]) -> ModelResponse:
        graph, rows, pending_holds = self._checked_graph(batches=batches)
        findings = [f for batch in batches for f in batch.findings] + graph.findings
        if self.request.discovery_continuation and not self.config.binding_contract:
            findings.extend(self._bind_continuation_edges(graph=graph, batches=batches))
        for claim_id, finding in self.edge_findings.items():
            findings.extend(
                finding.model_copy(update={"claim_id": origin})
                for origin in graph.origins[claim_id]
            )
        groups = _closed_components(rows)
        if len(groups) > 1:
            findings.append(
                Finding(stage="connectivity", detail=f"Review {len(groups)} separate components.")
            )
        assembled = rows
        if self.uses_mention_table:
            rows = evidence_binding.project_claims(rows=rows, approved=self.approved)
        names = proposal_names(claims=rows)
        if self.held_recovery.recovered:
            held_endpoints.append_overlay(
                recovery=self.held_recovery, rows=rows, names=names, origins=graph.origins
            )
        for follow_up in self.focused_omissions:
            focused_omissions.append(
                rows=rows, names=names, origins=graph.origins, additions=follow_up.additions
            )
        return self._finish_output(
            batches=batches,
            graph=graph,
            rows=rows,
            names=names,
            assembled=assembled,
            groups=groups,
            findings=findings,
            pending_holds=pending_holds,
        )

    def _bind_continuation_edges(
        self, *, graph: ClaimGraph, batches: Sequence[BatchResult]
    ) -> list[Finding]:
        held = held_endpoints.assembly_holds(graph=graph, batches=batches)
        prior = self.held_recovery.recovered
        resolved = {item.edge.claim_id for item in prior}
        for claim_id in resolved:
            _ = held.pop(claim_id, None)
        additions = continuation_bindings.recover(
            graph=graph,
            held=list(held.values()),
            inputs=self.request.inputs,
            reserved=self.approved
            | self.pending_concepts.keys()
            | {concept.name for item in prior for concept in item.concepts},
        )
        if additions and not self._fits_held_overlay(graph=graph, recovered=[*prior, *additions]):
            additions = []
        held.update({item.claim.claim_id: item for item in self.held_recovery.held})
        resolved.update(item.edge.claim_id for item in additions)
        self.held_recovery = held_endpoints.Recovery(
            held=[item for key, item in held.items() if key not in resolved],
            recovered=[*prior, *additions],
        )
        return [
            Finding(
                stage="binding",
                claim_id=item.edge.claim_id,
                name=item.edge.name,
                detail="Bound the verified assertion to exact participants in its sentence.",
            )
            for item in additions
        ]

    def _checked_graph(
        self, *, batches: list[BatchResult]
    ) -> tuple[ClaimGraph, list[IdentifiedClaim], dict[str, held_endpoints.HeldClaim]]:
        graph = self._assemble(batches)
        include_verified_evidence(graph=graph, batches=batches)
        rows = [c for c in graph.claims if c.claim_id not in self.edge_findings]
        pending_holds = self._pending_endpoint_holds(rows=rows)
        rows = [claim for claim in rows if claim.claim_id not in pending_holds]
        for row in rows:
            for witness in self.endpoint_evidence.get(row.claim_id, ()):
                if witness not in row.evidence:
                    row.evidence.append(witness)
        return graph, rows, pending_holds

    def _finish_output(  # noqa: PLR0913 - Render the exact assembled and checked projection.
        self,
        *,
        batches: list[BatchResult],
        graph: ClaimGraph,
        rows: list[IdentifiedClaim],
        names: dict[str, str],
        assembled: list[IdentifiedClaim],
        groups: list[list[str]],
        findings: list[Finding],
        pending_holds: dict[str, held_endpoints.HeldClaim],
    ) -> ModelResponse:
        binding = (
            self._binding_output(
                batches=batches,
                graph=graph,
                assembled=assembled,
                names=names,
            ).model_dump_json()
            if self.stable_binding
            else None
        )
        if self.repair_index is not None:
            repair = endpoint_repair.project(
                graph=graph,
                accepted_rows=assembled,
                batches=batches,
                names=names,
                index=self.repair_index,
                aliases={
                    name: alias
                    for name, alias in self.aliases.items()
                    if isinstance(alias, VerifiedAlias)
                },
            )
            rows = repair.rows
            binding = repair.binding.model_dump_json()
            findings.extend(
                Finding(stage="binding", claim_id=edge.claim_id, detail=edge.reason)
                for edge in repair.binding.edges
                if edge.reason is not None
            )
        rows, names = self._stage_pending_relationships(rows=rows, names=names, holds=pending_holds)
        output = _sdk_rows(rows, names=names)
        projection = {
            origin: names[c.claim_id] for c in rows for origin in graph.origins[c.claim_id]
        }
        self._report(
            batches=batches, rows=rows, groups=groups, findings=findings, projection=projection
        )
        models = sorted({r.model_id for r in self.receipts})
        return ModelResponse(
            output_json=json.dumps(output),
            model_id=",".join(models) if models else "domain-kernel/stage-without-receipt",
            provider_endpoint=next(
                (r.provider_endpoint for r in self.receipts if r.provider_endpoint), None
            ),
            input_tokens=sum(r.input_tokens or 0 for r in self.receipts),
            output_tokens=sum(r.output_tokens or 0 for r in self.receipts),
            discovery_binding_json=binding,
            discovery_coverage_json=omission_windows.WindowManifest(
                windows=self.omission_windows
            ).model_dump_json()
            if self.config.resumable_omissions
            else None,
            discovery_held_json=held_endpoints.HeldClaims(
                held=[
                    *self.held_recovery.held,
                    *(
                        item.model_copy(update={"proposal_name": names.get(key)})
                        if item.proposal_name is not None
                        else item
                        for key, item in pending_holds.items()
                    ),
                ]
            ).model_dump_json()
            if self.held_recovery.held or pending_holds
            else None,
        )

    def _stage_pending_relationships(
        self,
        *,
        rows: list[IdentifiedClaim],
        names: dict[str, str],
        holds: dict[str, held_endpoints.HeldClaim],
    ) -> tuple[list[IdentifiedClaim], dict[str, str]]:
        candidates = [
            item.claim
            for item in holds.values()
            if item.proposal_name is not None and item.claim.claim_id not in names
        ]
        if not candidates:
            return rows, names
        staged_rows, staged_names = list(rows), dict(names)
        held_endpoints.append_relationships(edges=candidates, rows=staged_rows, names=staged_names)
        limit = self.request.discovery_output_bytes
        if (
            limit is not None
            and len(json.dumps(_sdk_rows(rows=staged_rows, names=staged_names)).encode()) > limit
        ):
            return rows, names
        return staged_rows, staged_names

    def _pending_endpoint_holds(
        self, *, rows: Sequence[IdentifiedClaim]
    ) -> dict[str, held_endpoints.HeldClaim]:
        if not self.pending_concepts:
            return {}
        concepts = {c.name: c for c in rows if c.kind == "concept"}
        result: dict[str, held_endpoints.HeldClaim] = {}
        for claim in rows:
            endpoints = tuple(name for name in (claim.source, claim.target) if name is not None)
            pending = {
                name: self.pending_concepts[name][0]
                for name in endpoints
                if name in self.pending_concepts
            }
            if not pending:
                continue
            locally_verified = (
                bool(self.request.discovery_continuation)
                and not self.config.binding_contract
                and pending.keys() <= concepts.keys()
                and held_endpoints.cites_local_endpoints(
                    claim=claim,
                    concepts=[concepts[name] for name in endpoints if name in concepts],
                    inputs=self.request.inputs,
                )
            )
            result[claim.claim_id] = held_endpoints.HeldClaim(
                claim=claim,
                reason="Review the concept proposed in an earlier discovery run.",
                dependency_ids=list(dict.fromkeys(pending.values())),
                proposal_name=claim.name if locally_verified else None,
            )
        return result

    def _binding_output(
        self,
        *,
        batches: list[BatchResult],
        graph: ClaimGraph,
        assembled: list[IdentifiedClaim],
        names: Mapping[str, str],
    ) -> endpoint_contract.BindingEnvelope:
        edges: list[endpoint_contract.EdgeBinding] = []
        covered: set[str] = set()
        extracted = {
            claim.claim_id: claim
            for batch in reversed(batches)
            for claim in reversed(batch.candidates)
            if isinstance(claim, BoundClaim) and claim.kind == "relationship"
        }
        for claim in assembled:
            if isinstance(claim, BoundClaim) and claim.kind == "relationship":
                origins = graph.origins[claim.claim_id]
                covered.update(origins)
                edges.append(
                    self._edge_binding(
                        claim=claim,
                        proposal_name=names[claim.claim_id],
                        origins=origins,
                        original=extracted.get(claim.claim_id),
                    )
                )
        candidates = {
            claim.claim_id: claim
            for batch in batches
            for claim in (*batch.candidates, *batch.held, *batch.accepted)
            if isinstance(claim, BoundClaim) and claim.kind == "relationship"
        }
        candidates.update(
            (claim.claim_id, claim)
            for claim in graph.claims
            if isinstance(claim, BoundClaim) and claim.kind == "relationship"
        )
        held_reasons = {
            finding.claim_id: finding.detail
            for finding in (*graph.findings, *self.edge_findings.values())
        }
        held_reasons.update(
            (finding.claim_id, finding.detail)
            for batch in batches
            for finding in batch.findings
            if finding.stage == "binding"
        )
        edges.extend(
            self._edge_binding(
                claim=claim,
                proposal_name=None,
                origins=[claim_id],
                reason=held_reasons.get(
                    claim_id, "Review the source support for this relationship."
                ),
                original=extracted.get(claim_id),
            )
            for claim_id, claim in candidates.items()
            if claim_id not in covered
        )
        unresolved = {item.claim_id: item for batch in batches for item in batch.unbound}
        edges.extend(
            endpoint_contract.EdgeBinding(
                claim_id=item.claim_id,
                proposal_name=None,
                source=None,
                target=None,
                evidence=item.evidence,
                identity_evidence=[],
                origin_claim_ids=[item.claim_id],
                reason=(
                    "At least one participant reference or required source quotation "
                    "could not be located."
                ),
            )
            for item in unresolved.values()
        )
        return endpoint_contract.BindingEnvelope(
            concepts={
                item.name: names[item.claim_id] for item in assembled if item.kind == "concept"
            },
            edges=edges,
        )

    def _edge_binding(
        self,
        *,
        claim: BoundClaim,
        proposal_name: str | None,
        origins: list[str],
        reason: str | None = None,
        original: BoundClaim | None = None,
    ) -> endpoint_contract.EdgeBinding:
        identity: list[Anchor] = []

        def reference(
            mention: LocatedMention | None,
            key: str | None,
        ) -> endpoint_contract.EndpointReference | None:
            if mention is None:
                return None
            if mention.identity_witness is not None:
                identity.append(mention.identity_witness)
            elif isinstance(alias := self.aliases.get(mention.id), VerifiedAlias):
                identity.append(alias.identity_witness)
            if key is not None:
                key = self.approved_keys.get(key, key)
            return endpoint_contract.EndpointReference(occurrence=mention, concept_key=key)

        source = reference(claim.subject, claim.source)
        target = reference(claim.object, claim.target)
        return endpoint_contract.EdgeBinding(
            claim_id=claim.claim_id,
            proposal_name=proposal_name,
            source=source,
            target=target,
            evidence=self.endpoint_evidence.get(claim.claim_id, claim.evidence),
            identity_evidence=identity,
            origin_claim_ids=origins,
            reason=reason,
            previous_source=(
                self._prior_endpoint(mention=original.subject, chosen=claim.subject)
                if original is not None
                else None
            ),
            previous_target=(
                self._prior_endpoint(mention=original.object, chosen=claim.object)
                if original is not None
                else None
            ),
        )

    def _prior_endpoint(
        self, *, mention: LocatedMention | None, chosen: LocatedMention | None
    ) -> endpoint_contract.EndpointReference | None:
        if mention is None or mention == chosen:
            return None
        key = mention.endpoint
        return endpoint_contract.EndpointReference(
            occurrence=mention, concept_key=self.approved_keys.get(key, key)
        )

    def _report(
        self,
        *,
        batches: list[BatchResult],
        rows: Sequence[IdentifiedClaim],
        groups: list[list[str]],
        findings: list[Finding],
        projection: Mapping[str, str],
    ) -> None:
        report: dict[str, object] = {
            "version": 6
            if self.repaired_binding
            else (5 if self.stable_binding else 4 if self.config.binding_contract else 3),
            "proposal_names_by_claim_id": dict(projection),
            "verification": self.config.verification,
            "aliases": [a.model_dump() for a in self.aliases.values()],
            "profile": self.config.profile,
            "batches": [b.model_dump() for b in batches],
            "claims": [c.model_dump() for c in rows],
            "components": groups,
            "findings": [f.model_dump() for f in findings],
            "locators": [
                {
                    "revision": p.evidence[0].source.revision_id.value,
                    "locator": asdict(p.evidence[0].locator),
                    "parser": p.evidence[0].processing.parser_version,
                }
                for p in self.request.inputs
            ],
        }
        if self.focused_omissions:
            report["focused_omissions"] = [result.model_dump() for result in self.focused_omissions]
        if self.config.scope_shadow:
            report["scope_shadow"] = asdict(
                scope_shadow.inspect(rows=rows, inputs=self.request.inputs)
            )
        if self.decisions_audit is not None:
            report["endpoint_decisions"] = self.decisions_audit.model_dump()
        if self.config.stage_routes:
            report["stage_routes"] = {
                stage.value: r.profile for stage, r in self.config.stage_routes.items()
            }
            report["receipts"] = [receipt.model_dump() for receipt in self.receipts]
        if self.config.retain_responses:
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.request.request_id):
                raise InferenceError(message="Use a safe run identifier for the audit report.")
            path = self.config.directory / (self.request.request_id + ".json")
            if contract := self.config.binding_contract or self.source_identity_policy:
                report["contract"] = contract
                path = (
                    self.config.directory
                    / self.request.request_id
                    / (self.checkpoint_key + ".json")
                )
            write_private(
                path=path,
                payload=json.dumps(report, ensure_ascii=False, indent=2).encode(),
            )


def _sdk_rows(
    rows: Sequence[IdentifiedClaim], *, names: Mapping[str, str]
) -> dict[str, list[dict[str, object]]]:
    output: dict[str, list[dict[str, object]]] = {"concepts": [], "relationships": []}
    for c in rows:
        if isinstance(c, BoundClaim):
            meaning = evidence_binding.qualified_meaning(c)
        else:
            meaning = c.meaning
            for label, qualifications in (
                ("Conditions", c.conditions),
                ("Exceptions", c.exceptions),
            ):
                if qualifications:
                    meaning += " " + label + ": " + " ".join(q.text for q in qualifications)
        item: dict[str, object] = {
            "name": names[c.claim_id],
            "display_name": c.title,
            "meaning": meaning,
            "citations": list(
                dict.fromkeys(
                    a.citation for q in (c, *c.conditions, *c.exceptions) for a in q.evidence
                )
            ),
            "confidence": None,
        }
        if c.kind == "relationship":
            item.update(source=c.source, target=c.target)
        output["concepts" if c.kind == "concept" else "relationships"].append(item)
    return output
