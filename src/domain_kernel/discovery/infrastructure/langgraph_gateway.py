"""Optional staged document discovery. Approved model state belongs to the SDK."""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, TypedDict, final, override, runtime_checkable

from pydantic import BaseModel, TypeAdapter, ValidationError

from domain_kernel._shared.application.inference import (
    InferenceInput,
    ModelGateway,
    ModelRequest,
    ModelResponse,
)
from domain_kernel._shared.domain.naming import LOOKUP_NAME_PATTERN
from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.discovery.application.claim_extraction import (
    CHECK_EDGES,
    EXTRACT,
    OMISSIONS,
    RECONCILE,
    REPAIR,
    VERIFY,
    Alias,
    Aliases,
    Anchor,
    BatchResult,
    Claim,
    Claims,
    Finding,
    Verdicts,
    cross_references,
    normalized,
)
from domain_kernel.discovery.application.structured_output import output_error, response_schema
from domain_kernel.discovery.infrastructure.checkpoints import (
    Checkpoint,
    Receipt,
    StageCheckpoints,
    write_private,
)
from domain_kernel.discovery.infrastructure.local_replay import LocalReplayGateway
from domain_kernel.shared.errors import InferenceError, MissingCapabilityError
from domain_kernel.shared.hashing import canonical_json_bytes, hash_json
from domain_kernel.sources.domain.parsed import DocumentSpan

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Iterable, Iterator, Sequence
    from pathlib import Path

    from domain_kernel.discovery.infrastructure.mentions import NamedEntityHints


class _Approved(BaseModel):
    name: str
    meaning: str
    kind: str | None = None


class _Context(BaseModel):
    approved_meanings: tuple[_Approved, ...] = ()


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


async def _complete_batches(
    calls: Iterable[Coroutine[object, object, BatchResult]],
) -> list[BatchResult]:
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
    covered: dict[object, set[int]] = defaultdict(set)
    for part in request.inputs:
        if (pages := _native_pages(part)) is not None:
            covered[part.evidence[0].source].update(pages)
    batches: list[BatchResult] = []
    size = 0
    for index, part in enumerate(request.inputs, start=1):
        evidence = part.evidence[0]
        if len(part.evidence) != 1:
            raise InferenceError(message="Staged extraction requires one locator per passage.")
        loc = evidence.locator
        if (
            _native_pages(part) is None
            and evidence.source in covered
            and isinstance(loc, DocumentSpan)
            and (
                (loc.section is None and loc.page in covered[evidence.source])
                or (loc.page is None and not covered[evidence.source])
            )
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


_ALIAS_GROUP_LIMIT = 24
_MIN_ALIAS_TOKEN = 3


def _alias_groups(concepts: dict[str, Claim]) -> Iterator[list[Claim]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for name in sorted(concepts):
        for token in sorted(set(name.split("-"))):
            if len(token) >= _MIN_ALIAS_TOKEN:
                groups[token].append(name)
    seen: set[tuple[str, ...]] = set()
    for names in groups.values():
        if tuple(names) in seen:
            continue
        seen.add(tuple(names))
        for start in range(0, len(names), _ALIAS_GROUP_LIMIT):
            group = names[start : start + _ALIAS_GROUP_LIMIT]
            if len(group) > 1:
                yield [concepts[name] for name in group]


def _closed_components(rows: list[Claim]) -> list[list[str]]:
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


@dataclass(frozen=True, kw_only=True)
class LangGraphDiscoveryGateway(ModelGateway):
    """Process a scoped discovery request with local, resumable stage receipts.

    Use a private directory per tenant and a profile identifying the underlying
    endpoint, model and inference settings. Retained stage responses enable replay.
    """

    gateway: ModelGateway | None
    directory: Path
    profile: str
    batch_bytes: int = 48_000
    concurrency: int = 3
    max_request_bytes: int = 512_000
    mention_detector: NamedEntityHints | None = None
    retain_responses: bool = True

    def __post_init__(self) -> None:
        """Validate the bounds before opening a journal or scheduling work."""
        if type(self.batch_bytes) is not int or self.batch_bytes < 1:
            raise ValueError("Set a positive batch byte limit.")
        if type(self.max_request_bytes) is not int or self.max_request_bytes <= 0:
            raise ValueError("Set a positive serialized request limit.")
        if type(self.concurrency) is not int or self.concurrency < 1:
            raise ValueError("Set positive inference concurrency.")

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
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
        stages = (
            ("extract", execution.extract),
            ("coverage", execution.coverage),
            ("verify", execution.verify),
            ("repair", execution.repair),
            ("reconcile", execution.reconcile),
            ("edges", execution.check_edges),
        )
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


_STATE = TypeAdapter(_State)


@final
class _Execution:
    def __init__(self, *, config: LangGraphDiscoveryGateway, request: ModelRequest) -> None:
        self.config = config
        self.request = request
        self.recording = LocalReplayGateway(
            path=config.directory / "stages.sqlite3",
            profile=config.profile,
            gateway=config.gateway,
            retain_responses=config.retain_responses,
        )
        self.slots = asyncio.Semaphore(config.concurrency)
        self.receipts: list[Receipt] = []
        intent = hash_json(
            value=record_value(
                value=(
                    "document-graph-v3",
                    (EXTRACT, OMISSIONS, VERIFY, REPAIR, RECONCILE, CHECK_EDGES),
                    tuple(
                        json.dumps(schema.model_json_schema())
                        for schema in (Claims, Verdicts, Aliases)
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
                )
            )
        )
        self.checkpoints = StageCheckpoints(
            directory=config.directory / "checkpoints", key=intent.value.removeprefix("sha256:")
        )
        self.aliases: dict[str, Alias] = {}
        self.edge_findings: dict[str, Finding] = {}
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
                )
                await asyncio.to_thread(self.checkpoints.save, checkpoint=snapshot)
            return result

        return checkpoint

    def part(self, index: int) -> InferenceInput:
        return self.request.inputs[index - 1]

    async def call[T: BaseModel](
        self,
        *,
        schema: type[T],
        prompt: str,
        indexes: list[int],
        context: dict[str, object],
        inputs: Sequence[InferenceInput] | None = None,
    ) -> T:
        context["model_context"] = json.loads(self.request.context_json or "{}")
        stage = replace(
            self.request,
            instructions=prompt,
            inputs=tuple(self.part(i) for i in indexes) if inputs is None else inputs,
            context_json=json.dumps(context, ensure_ascii=False, sort_keys=True),
            response_schema_json=json.dumps(schema.model_json_schema()),
            timeout_seconds=min(self.request.timeout_seconds, 150.0),
        )
        envelope = record_value(
            value=(
                stage.instructions,
                stage.context_json,
                stage.response_schema_json,
                tuple((p.text, p.evidence) for p in stage.inputs),
            )
        )
        if len(canonical_json_bytes(value=envelope)) > self.config.max_request_bytes:
            raise InferenceError(
                message="The framed stage request exceeds the byte limit. Reduce the batch size."
            )
        async with self.slots:
            response = await self.recording.generate(request=stage)
        self.receipts.append(
            Receipt(
                model_id=response.model_id,
                provider_endpoint=response.provider_endpoint,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
        )
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

    def anchor(self, *, anchor: Anchor, indexes: list[int]) -> Anchor | None:
        quote = normalized(anchor.quote)
        if not quote or not 1 <= anchor.citation <= len(indexes):
            return None
        i = indexes[anchor.citation - 1]
        part = self.part(i)
        if quote not in normalized(part.text):
            return None
        for page in _native_pages(part) or ():
            physical = self.pages.get((part.evidence[0].source, page))
            if physical and quote in normalized(self.part(physical).text):
                return Anchor(citation=physical, quote=anchor.quote)
        return Anchor(citation=i, quote=anchor.quote)

    def resolve(self, claim: Claim, indexes: list[int]) -> Claim | None:
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
        return result

    async def extract(self, state: _State) -> _State:
        return {
            "batches": await _complete_batches(
                self.mine(batch, i, omissions=False) for i, batch in enumerate(state["batches"])
            )
        }

    async def coverage(self, state: _State) -> _State:
        return {
            "batches": await _complete_batches(
                self.mine(batch, i, omissions=True) for i, batch in enumerate(state["batches"])
            )
        }

    async def mine(self, batch: BatchResult, number: int, *, omissions: bool) -> BatchResult:
        result = batch.model_copy(deep=True)
        context: dict[str, object] = {}
        if omissions:
            context["prior_claims"] = [(c.name, c.meaning) for c in result.candidates]
            if self.config.mention_detector:
                context["mention_profile"] = self.config.mention_detector.profile
                context["mentions"] = [
                    {"citation": n, **hint.model_dump()}
                    for n, i in enumerate(batch.passages, 1)
                    for hint in self.config.mention_detector(self.part(i).text)
                ]
        rows = await self.call(
            schema=Claims,
            prompt=self.request.instructions + "\n" + (OMISSIONS if omissions else "") + EXTRACT,
            indexes=batch.passages,
            context=context,
        )
        for row in rows.claims:
            claim = self.resolve(row, batch.passages)
            if claim is None:
                result.findings.append(
                    Finding(
                        stage="lineage",
                        batch=number,
                        name=row.name,
                        detail="Check claim shape and exact supporting quotations.",
                    )
                )
            elif claim not in result.candidates:
                result.candidates.append(claim)
        return result

    async def verify(self, state: _State) -> _State:
        return {
            "batches": await _complete_batches(
                self.check(batch, i) for i, batch in enumerate(state["batches"])
            )
        }

    async def check(self, batch: BatchResult, number: int) -> BatchResult:
        if not batch.candidates:
            return batch
        result = batch.model_copy(deep=True)
        cited = list(
            dict.fromkeys(
                a.citation
                for c in batch.candidates
                for qualified in (c, *c.conditions, *c.exceptions)
                for a in qualified.evidence
            )
        )
        wanted = cross_references(
            text=" ".join(a.quote for c in batch.candidates for a in c.evidence)
        )
        referenced = [
            i
            for i, part in enumerate(self.request.inputs, 1)
            if i not in cited
            and any(
                line.strip().casefold().rstrip(".:") in wanted for line in part.text.splitlines()
            )
        ]
        indexes = list(cited)
        for i in referenced[:3]:
            if (
                sum(len(self.part(j).text.encode()) for j in (*indexes, i))
                <= self.config.batch_bytes
            ):
                indexes.append(i)
        local = {value: i for i, value in enumerate(indexes, 1)}
        claims = [c.model_copy(deep=True) for c in batch.candidates]
        for claim in claims:
            for qualified in (claim, *claim.conditions, *claim.exceptions):
                for a in qualified.evidence:
                    a.citation = local[a.citation]
        verdicts = await self.call(
            schema=Verdicts,
            prompt=VERIFY,
            indexes=indexes,
            context={"claims": [c.model_dump() for c in claims]},
        )
        for i, candidate in enumerate(result.candidates):
            decisions = [v for v in verdicts.verdicts if v.index == i]
            if len(decisions) == 1 and decisions[0].status == "supported":
                result.accepted.append(candidate)
            else:
                detail = (
                    decisions[0].status + ": " + decisions[0].reason
                    if len(decisions) == 1
                    else "Missing or ambiguous verdict."
                )
                result.findings.append(
                    Finding(stage="semantic", batch=number, name=candidate.name, detail=detail)
                )
        return result

    async def repair(self, state: _State) -> _State:
        return {
            "batches": await _complete_batches(
                self.repair_batch(batch, i) for i, batch in enumerate(state["batches"])
            )
        }

    async def repair_batch(self, batch: BatchResult, number: int) -> BatchResult:
        disputed = {f.name: f.detail for f in batch.findings if f.stage == "semantic"}
        if not disputed:
            return batch
        originals = {(c.name, c.kind) for c in batch.candidates if c.name in disputed}
        rows = await self.call(
            schema=Claims,
            prompt=REPAIR + EXTRACT,
            indexes=batch.passages,
            context={
                "disputed_claims": [
                    (c.name, c.meaning, disputed[c.name])
                    for c in batch.candidates
                    if c.name in disputed
                ]
            },
        )
        repairs = [
            resolved
            for row in rows.claims
            if (row.name, row.kind) in originals
            and (resolved := self.resolve(row, batch.passages)) is not None
        ]
        if not repairs:
            return batch
        checked = await self.check(BatchResult(passages=batch.passages, candidates=repairs), number)
        result = batch.model_copy(deep=True)
        result.candidates.extend(repairs)
        result.accepted.extend(checked.accepted)
        result.findings.extend(checked.findings)
        return result

    async def reconcile(self, state: _State) -> _State:
        concepts = {c.name: c for b in state["batches"] for c in b.accepted if c.kind == "concept"}
        for rows in _alias_groups(concepts):
            inputs = [
                InferenceInput(
                    text=c.evidence[0].quote,
                    evidence=self.part(c.evidence[0].citation).evidence,
                )
                for c in rows
            ]
            result = await self.call(
                schema=Aliases,
                prompt=RECONCILE,
                indexes=[],
                inputs=inputs,
                context={
                    "concepts": [
                        {"name": c.name, "meaning": c.meaning, "quote": c.evidence[0].quote}
                        for c in rows
                    ]
                },
            )
            visible = {c.name: c for c in rows}
            for alias in result.aliases:
                if self.valid_alias(alias, visible):
                    self.aliases[alias.alternate] = alias
        return state

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
        rows, _ = self._assemble(state["batches"])
        context = _Context.model_validate_json(self.request.context_json or "{}")
        meanings = {item.name: item.meaning for item in context.approved_meanings}
        meanings.update({c.name: c.meaning for c in rows if c.kind == "concept"})
        edges = [c for c in rows if c.kind == "relationship"]
        for start in range(0, len(edges), 8):
            group = edges[start : start + 8]
            evidence = [
                a for c in group for q in (c, *c.conditions, *c.exceptions) for a in q.evidence
            ]
            indexes = list(dict.fromkeys(a.citation for a in evidence))
            snippets = [
                InferenceInput(
                    text="\n".join(dict.fromkeys(a.quote for a in evidence if a.citation == i)),
                    evidence=self.part(i).evidence,
                )
                for i in indexes
            ]
            inspect: list[dict[str, object]] = []
            for c in group:
                linked = c.model_copy(deep=True)
                for q in (linked, *linked.conditions, *linked.exceptions):
                    for anchor in q.evidence:
                        anchor.citation = indexes.index(anchor.citation) + 1
                inspect.append(
                    {
                        "edge": linked.model_dump(),
                        "subject_meaning": meanings.get(c.source or ""),
                        "target_meaning": meanings.get(c.target or ""),
                    }
                )
            grades = await self.call(
                schema=Verdicts,
                prompt=CHECK_EDGES,
                indexes=indexes,
                inputs=snippets,
                context={"edges": inspect},
            )
            for i, c in enumerate(group):
                votes = [v for v in grades.verdicts if v.index == i]
                if len(votes) != 1 or votes[0].status != "supported":
                    self.edge_findings[c.name] = Finding(
                        stage="endpoints",
                        name=c.name,
                        detail=votes[0].reason
                        if len(votes) == 1
                        else "Missing or ambiguous endpoint verdict.",
                    )
        return state

    def _assemble(self, batches: list[BatchResult]) -> tuple[list[Claim], list[Finding]]:
        findings = [f for batch in batches for f in batch.findings]
        chosen: dict[str, Claim] = {}
        for batch in batches:
            for c in batch.accepted:
                if c.name not in chosen:
                    chosen[c.name] = c
                elif chosen[c.name] != c:
                    findings.append(
                        Finding(
                            stage="reconcile",
                            name=c.name,
                            detail="Multiple formulations. Inspect the retained alternatives.",
                        )
                    )
        rows = self._resolve_edges(chosen=chosen, findings=findings)
        return rows, findings

    def finish(self, *, batches: list[BatchResult]) -> ModelResponse:
        assembled, findings = self._assemble(batches)
        rows = [c for c in assembled if c.name not in self.edge_findings]
        findings.extend(self.edge_findings.values())
        groups = _closed_components(rows)
        if len(groups) > 1:
            findings.append(
                Finding(stage="connectivity", detail=f"Review {len(groups)} separate components.")
            )
        output = _sdk_rows(rows)
        self._report(batches=batches, rows=rows, groups=groups, findings=findings)
        models = sorted({r.model_id for r in self.receipts})
        return ModelResponse(
            output_json=json.dumps(output),
            model_id=",".join(models),
            provider_endpoint=next(
                (r.provider_endpoint for r in self.receipts if r.provider_endpoint), None
            ),
            input_tokens=sum(r.input_tokens or 0 for r in self.receipts),
            output_tokens=sum(r.output_tokens or 0 for r in self.receipts),
        )

    def _resolve_edges(self, *, chosen: dict[str, Claim], findings: list[Finding]) -> list[Claim]:
        for alternate in self.aliases:
            _ = chosen.pop(alternate, None)
        names = {c.name for c in chosen.values() if c.kind == "concept"}
        context = _Context.model_validate_json(self.request.context_json or "{}")
        names.update(item.name for item in context.approved_meanings if item.kind == "concept")
        rows: list[Claim] = []
        for original in chosen.values():
            c = original.model_copy(deep=True)
            if c.source in self.aliases:
                c.source = self.aliases[c.source].preferred
            if c.target in self.aliases:
                c.target = self.aliases[c.target].preferred
            if c.kind == "relationship" and (c.source not in names or c.target not in names):
                findings.append(
                    Finding(
                        stage="reconcile",
                        name=c.name,
                        detail="Unresolved endpoint; keep for review.",
                    )
                )
            else:
                rows.append(c)
        return rows

    def _report(
        self,
        *,
        batches: list[BatchResult],
        rows: list[Claim],
        groups: list[list[str]],
        findings: list[Finding],
    ) -> None:
        report = {
            "version": 1,
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
        if self.config.retain_responses:
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.request.request_id):
                raise InferenceError(message="Use a safe run identifier for the audit report.")
            write_private(
                path=self.config.directory / (self.request.request_id + ".json"),
                payload=json.dumps(report, ensure_ascii=False, indent=2).encode(),
            )


def _sdk_rows(rows: list[Claim]) -> dict[str, list[dict[str, object]]]:
    output: dict[str, list[dict[str, object]]] = {"concepts": [], "relationships": []}
    for c in rows:
        meaning = c.meaning
        for label, qualifications in (
            ("Conditions", c.conditions),
            ("Exceptions", c.exceptions),
        ):
            if qualifications:
                meaning += " " + label + ": " + " ".join(q.text for q in qualifications)
        item: dict[str, object] = {
            "name": c.name,
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
