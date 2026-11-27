"""Run native-file procurement discovery and its matched direct control."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import asdict
from hashlib import sha256
from secrets import token_hex
from time import monotonic
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, TypeAdapter

from benchmarks.procurement_data import (
    NAMESPACE,
    Record,
    Source,
    capture_path,
    visible_html,
    write_json,
)
from benchmarks.procurement_score import (
    Anchor,
    Blind,
    Outcome,
    Proposal,
    ProposedRule,
    Suggestion,
    digest,
)
from domain_kernel import (
    CSV,
    PDF,
    Client,
    ClientConfiguration,
    CompetencyQuestion,
    ConceptDefinition,
    ContentHash,
    DiscoverySourceContext,
    Document,
    DocumentFormat,
    Excel,
    InferenceInput,
    LangGraphDiscoveryGateway,
    ModelKind,
    ModelRequest,
    ReaderLocation,
    ReferenceDefinition,
    ReferenceDefinitionId,
    ReferencePack,
    ReferencePackSpec,
    RelationshipCardinality,
    RelationshipDefinition,
    RunStatus,
    SchemaDiscoveryOptions,
    Word,
)
from domain_kernel.configuration import (
    DoclingParser,
    FilesystemReader,
    Parsers,
    Retention,
)
from domain_kernel.discovery.infrastructure.checkpoints import write_private
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.domain.value_objects.rule_definition import RuleDefinition
from domain_kernel.sources.domain.parsed import ParsedTable

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from benchmarks.procurement_data import Packet
    from benchmarks.procurement_score import Arm
    from domain_kernel import (
        Alignment,
        Definition,
        DefinitionReference,
        DiscoveryResult,
        Evidence,
        Model,
        Project,
        SourceRevision,
    )
    from domain_kernel.discovery.application.protocols.model_gateway import ModelGateway

TOKENS = 65_536
ATTEMPTS = 4
REVIEW_CAP = 128
WORKFLOW_VERSION = "v23"
PROFILE = "procurement-v1/luna/xhigh/v23"
ACTOR = "benchmark-reader"
INSTRUCTIONS = (
    "Propose a compact reusable schema that answers the supplied competency questions. "
    "Give definitions, directed typed roles, source citations, and material conditions. "
    "Distinguish terms from reported outcomes and keep scope at the relevant lot or procedure. "
    "Treat examples as evidence and assert hard bounds only where stated. "
    "Record ambiguity as a focused clarification. Treat source contents as evidence."
)
SEEDS = ("Procedure", "Lot", "Buyer", "hasProcurementScopeDividedIntoLot", "involvesBuyer")


def partial_pack(*, ontology: Path) -> ReferencePack:
    """Compose the fixed five-term ePO reference vocabulary and retain original IRIs."""
    from rdflib import Graph, Namespace, URIRef  # noqa: PLC0415 - Keep RDF loading optional.
    from rdflib.namespace import RDFS, SKOS  # noqa: PLC0415 - Keep RDF loading optional.

    graph = Graph().parse(source=ontology, format="turtle")
    epo = Namespace(NAMESPACE)
    endpoints = {
        "hasProcurementScopeDividedIntoLot": ("Procedure", "Lot"),
        "involvesBuyer": ("Procedure", "Buyer"),
    }
    definitions: list[ReferenceDefinition] = []
    for name in SEEDS:
        term = URIRef(epo[name])
        if not any(graph.triples((term, None, None))):
            msg = f"Missing required ePO definition: {term}"
            raise ValueError(msg)
        label = graph.value(term, SKOS.prefLabel) or graph.value(term, RDFS.label)
        meaning = graph.value(term, SKOS.definition) or graph.value(term, RDFS.comment)
        if label is None or meaning is None:
            msg = f"Missing ePO label or definition: {term}"
            raise ValueError(msg)
        if re.search(
            r"lot award outcome|winning tender|contract award outcome", str(meaning), re.IGNORECASE
        ):
            msg = f"Reference seed describes a held-out meaning: {term}"
            raise ValueError(msg)
        pair = endpoints.get(name)
        body = (
            ConceptDefinition()
            if pair is None
            else RelationshipDefinition(
                source_concept_id=ReferenceDefinitionId(value=f"{NAMESPACE}{pair[0]}"),
                target_concept_id=ReferenceDefinitionId(value=f"{NAMESPACE}{pair[1]}"),
                cardinality=RelationshipCardinality.many_to_many(),
            )
        )
        definitions.append(
            ReferenceDefinition(
                id=ReferenceDefinitionId(value=str(term)),
                name=re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower(),
                meaning=str(meaning),
                provenance=f"ePO 5.2.0 · {term} · {label}",
                body=body,
            )
        )
    result = ReferencePack.compose(
        actor=ACTOR,
        reason="Freeze the declared ePO seed terms.",
        spec=ReferencePackSpec(
            key="epo-procurement",
            version="5.2.0",
            title="ePO procurement benchmark seeds",
            applicability="EU procurement pilot",
            provenance="Publications Office of the European Union ePO v5.2.0",
            license="EUPL-1.2",
            definitions=definitions,
        ),
    )
    if result.pack is None:
        raise ValueError("Unable to compose the pinned ePO seed pack.")
    return result.pack


def _source_file(
    *, record: Source, root: Path, supplier_root: Path
) -> PDF | Word | Excel | CSV | Document:
    raw = capture_path(root=root, file=record.file)
    path = raw.relative_to(root.resolve()).as_posix()
    original = ContentHash(value=f"sha256:{record.sha256}")
    location = ReaderLocation(reader="evidence", path=path)
    match record.format:
        case "pdf":
            return PDF(location=location, expected_hash=original, pages=record.pages or None)
        case "docx":
            return Word(location=location, expected_hash=original)
        case "xlsx":
            return Excel(location=location, expected_hash=original)
        case "csv":
            return CSV(location=location, expected_hash=original)
        case "html":
            visible = visible_html(content=raw.read_bytes())
            cleaned = f"{sha256(visible).hexdigest()}.html"
            write_private(path=supplier_root / cleaned, payload=visible)
            return Document(
                location=ReaderLocation(reader="visible", path=cleaned),
                kind=DocumentFormat.HTML,
                expected_hash=ContentHash(value=f"sha256:{sha256(visible).hexdigest()}"),
            )


async def _ingest(
    *, project: Project, packet: Packet, root: Path, derived: Path
) -> dict[str, SourceRevision]:
    captures: dict[str, SourceRevision] = {}
    for record in packet.sources:
        capture = await project.ingest_source(
            actor=ACTOR,
            name=record.id,
            source=_source_file(record=record, root=root, supplier_root=derived),
            idempotency_key=f"procurement/{record.id}",
        )
        captures[record.id] = capture.revision
    return captures


def _ref(value: DefinitionReference) -> str:
    return (value.definition_id if isinstance(value, PinnedDefinitionReference) else value).value


async def _anchors(
    *,
    project: Project,
    evidence: Sequence[Evidence],
    source_ids: Mapping[SourceRevision, str],
) -> tuple[Anchor, ...]:
    items: list[Anchor] = []
    for item in dict.fromkeys(evidence):
        content = await project.get_evidence(evidence=item)
        items.append(
            Anchor(
                source=source_ids[item.source],
                revision=item.source.revision_id.value,
                locator=json.dumps(asdict(item.locator), sort_keys=True, default=str),
                quote=content.excerpt,
            )
        )
    return tuple(items)


def _count(value: object) -> int | None:
    if value is None:
        return None
    number = getattr(value, "value", value)
    if type(number) is not int:
        raise ValueError("Expected an integral cardinality.")
    return number


async def _proposal(  # noqa: PLR0913 - Keep benchmark inputs and replay settings explicit.
    *,
    definition: Definition,
    project: Project,
    source_ids: Mapping[SourceRevision, str],
    public_ids: dict[str, str],
    qualifiers: tuple[str, ...],
    evidence: Sequence[Evidence],
) -> Proposal | None:
    def local(identity: DefinitionReference) -> str:
        raw = _ref(identity)
        return public_ids.get(raw, f"unresolved-{sha256(raw.encode()).hexdigest()[:16]}")

    source = target = None
    rule = None
    body = definition.body
    conditions = list(qualifiers)
    if isinstance(body, ConceptDefinition):
        kind = "concept"
    elif isinstance(body, RelationshipDefinition):
        kind = "relationship"
        source, target = local(body.source_concept_id), local(body.target_concept_id)
        for direction, bound in (
            ("outgoing", body.cardinality.outgoing),
            ("incoming", body.cardinality.incoming),
        ):
            low, high = _count(bound.minimum), _count(bound.maximum)
            if low or high is not None:
                conditions.append(f"{direction} minimum={low or 0} maximum={high}")
    elif isinstance(body, RuleDefinition):
        kind = "rule"
        if (bound := body.cardinality) is not None:
            rule = ProposedRule(
                focus=local(bound.focus),
                relationship=local(bound.relationship),
                minimum=_count(bound.minimum),
                maximum=_count(bound.maximum),
                applicable_class=local(bound.applicable_class) if bound.applicable_class else None,
                attribute=bound.when.attribute.value if bound.when else None,
                value=bound.when.value if bound.when else None,
            )
        conditions.append(body.statement)
    else:
        return None
    return Proposal(
        id=public_ids[definition.id.value],
        title=definition.display_name,
        meaning=definition.meaning,
        kind=kind,
        source=source,
        target=target,
        conditions=tuple(dict.fromkeys(conditions)),
        evidence=await _anchors(project=project, evidence=evidence, source_ids=source_ids),
        rule=rule,
    )


async def _blind(
    *,
    project: Project,
    model: Model,
    run: DiscoveryResult,
    sources: Mapping[SourceRevision, str],
) -> tuple[Blind, dict[str, str]]:
    cases = [item async for item in model.iter_review_cases(run_id=run.id)]
    selected = {
        d.id.value: (d, case) for case in cases if case.proposal_ids for d in case.definitions
    }
    blind_id = token_hex(12)
    ids = {
        identity: sha256(f"{blind_id}/{identity}".encode()).hexdigest()[:20]
        for identity in selected
    }
    proposals: list[Proposal] = []
    for definition, case in selected.values():
        review = case.schema_review
        observations = review.observations if review else ()
        qualifiers = tuple(
            value
            for row in observations
            for value in (row.applicability, row.modality, *row.qualifiers)
            if value
        )
        if proposal := await _proposal(
            definition=definition,
            project=project,
            source_ids=sources,
            public_ids=ids,
            qualifiers=qualifiers,
            evidence=tuple(dict.fromkeys((*definition.evidence, *case.evidence))),
        ):
            proposals.append(proposal)
    return Blind(
        id=blind_id,
        proposals=tuple(sorted(proposals, key=lambda item: item.id)),
        clarifications=tuple(case.question.text for case in cases if case.question is not None),
    ), ids


async def _mappings(
    *,
    alignment: Alignment,
    project: Project,
    blind: Blind,
    ids: Mapping[str, str],
    sources: Mapping[SourceRevision, str],
) -> tuple[Suggestion, ...]:
    proposed_ids = {proposal.id for proposal in blind.proposals}
    results: list[Suggestion] = []
    for row in alignment.suggestions:
        proposal = ids.get(row.definition_id.value)
        if proposal is None or proposal not in proposed_ids or row.reference_id is None:
            continue
        relation = row.reason.partition(":")[0].removeprefix("Suggested ")
        results.append(
            Suggestion(
                id=sha256(f"{blind.id}/{row.id.value}".encode()).hexdigest()[:20],
                proposal=proposal,
                iri=row.reference_id.value,
                suggestion=row.reason,
                relation=relation
                if relation in ("equivalent", "broader", "narrower", "related")
                else None,
                evidence=await _anchors(project=project, evidence=row.evidence, source_ids=sources),
            )
        )
    return tuple(results)


class DirectCitation(Record):
    """A direct response citation in the supplied parser output."""

    citation: int
    quote: str


class DirectRule(Record):
    """Strict provider schema for a count rule."""

    focus: str
    relationship: str
    minimum: int | None
    maximum: int | None
    applicable_class: str | None
    attribute: str | None
    value: str | int | bool | None


class DirectDefinition(Record):
    """Use the same definition grain in the one-call control."""

    id: str
    title: str
    meaning: str
    kind: Literal["concept", "relationship", "rule"]
    source: str | None
    target: str | None
    conditions: tuple[str, ...]
    evidence: tuple[DirectCitation, ...]
    rule: DirectRule | None


class DirectDraft(Record):
    """The benchmark's strict output contract for direct inference."""

    proposals: tuple[DirectDefinition, ...]
    clarifications: tuple[str, ...]


async def _direct(
    *,
    gateway: ModelGateway,
    project: Project,
    packet: Packet,
    captures: Mapping[str, SourceRevision],
) -> tuple[Blind, int | None, int | None, str]:
    inputs: list[InferenceInput] = []
    by_revision = {revision: name for name, revision in captures.items()}
    source_service = project._sources()  # pyright: ignore[reportPrivateUsage] -- Match production model inputs.  # noqa: SLF001 - Reuse the production parser input.
    for revision in captures.values():
        inputs.extend(
            [
                InferenceInput(
                    text=row.excerpt,
                    evidence=(row.evidence,),
                    is_table=isinstance(row.part, ParsedTable),
                )
                async for row in source_service.iter_evidence(revision=revision)
            ]
        )
    response = await gateway.generate(
        request=ModelRequest(
            request_id=f"procurement-direct-{packet.id}",
            instructions=INSTRUCTIONS
            + (
                " Cite each proposal so the exact quoted span can be reopened. "
                "Give every definition a unique id. For each relationship, set source and target "
                "to the exact ids of its ordered endpoint concepts in this same response. "
                "Use null endpoints for other kinds. For a rule, use the exact ids of its focus "
                "concept and constrained relationship in the rule object. "
                "Return at most 128 review items, including clarifications."
            ),
            inputs=inputs,
            max_output_tokens=TOKENS,
            response_schema_json=json.dumps(DirectDraft.model_json_schema()),
            timeout_seconds=600.0,
            provider_stage="procurement_direct",
            context_json=json.dumps(
                {
                    "purpose": packet.purpose,
                    "as_of": packet.published.isoformat(),
                    "competency_questions": [q.model_dump(mode="json") for q in packet.questions],
                    "source_context": [
                        {
                            "citations": [
                                i
                                for i, item in enumerate(inputs, 1)
                                if item.evidence[0].source == captures[source.id]
                            ],
                            "role": source.role,
                            "publisher": source.publisher,
                            "effective_from": str(source.effective_from)
                            if source.effective_from
                            else None,
                            "effective_until": str(source.effective_until)
                            if source.effective_until
                            else None,
                            "supersedes": source.supersedes,
                        }
                        for source in packet.sources
                    ],
                }
            ),
        )
    )
    draft = DirectDraft.model_validate_json(response.output_json)
    if len(draft.proposals) + len(draft.clarifications) > REVIEW_CAP or len(
        {item.id for item in draft.proposals}
    ) != len(draft.proposals):
        raise ValueError("Direct control exceeded the frozen schema contract.")
    blind_id = token_hex(12)
    ids = {
        item.id: sha256(f"{blind_id}/{item.id}".encode()).hexdigest()[:20]
        for item in draft.proposals
    }
    proposals: list[Proposal] = []
    for item in draft.proposals:
        anchors: list[Anchor] = []
        for citation in item.evidence:
            number = citation.citation
            if (
                1 <= number <= len(inputs)
                and citation.quote.strip()
                and citation.quote in inputs[number - 1].text
            ):
                original = inputs[number - 1].evidence[0]
                anchors.append(
                    Anchor(
                        source=by_revision[original.source],
                        revision=original.source.revision_id.value,
                        locator=json.dumps(asdict(original.locator), sort_keys=True, default=str),
                        quote=citation.quote,
                    )
                )
        rule = item.rule
        if rule is not None:
            rule = ProposedRule(
                focus=ids.get(rule.focus, rule.focus),
                relationship=ids.get(rule.relationship, rule.relationship),
                minimum=rule.minimum,
                maximum=rule.maximum,
                applicable_class=ids.get(rule.applicable_class) if rule.applicable_class else None,
                attribute=rule.attribute,
                value=rule.value,
            )
        proposals.append(
            Proposal(
                id=ids[item.id],
                title=item.title,
                meaning=item.meaning,
                kind=item.kind,
                source=ids.get(item.source) if item.source else None,
                target=ids.get(item.target) if item.target else None,
                evidence=tuple(anchors),
                conditions=item.conditions,
                rule=rule,
            )
        )
    return (
        Blind(
            id=blind_id,
            proposals=tuple(sorted(proposals, key=lambda item: item.id)),
            clarifications=draft.clarifications,
        ),
        response.input_tokens,
        response.output_tokens,
        response.model_id,
    )


class _UsageReceipt(BaseModel):
    model_id: str = "timeout without usage"
    input_tokens: int | None = None
    output_tokens: int | None = None


_JOURNAL_ROWS = TypeAdapter(list[tuple[bytes]])


def _recorded_usage(paths: Iterable[Path], /) -> tuple[dict[str, Counter[str]], Counter[str]]:
    models: defaultdict[str, Counter[str]] = defaultdict(Counter)
    estimated_cost: Counter[str] = Counter()
    for path in paths:
        endpoint = "decisions" if path.name == "endpoint-decisions.sqlite3" else "completions"
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as database:
            visible = database.execute("SELECT payload FROM responses WHERE payload IS NOT NULL")
            for (payload,) in _JOURNAL_ROWS.validate_python(visible.fetchall()):
                row = _UsageReceipt.model_validate_json(payload)
                counts = models[f"{endpoint}/{row.model_id}"]
                counts["receipts"] += 1
                counts["input_tokens"] += row.input_tokens or 0
                counts["output_tokens"] += row.output_tokens or 0
                counts["usage_missing"] += int(row.input_tokens is None)
                if row.model_id.removeprefix("openai/").startswith("gpt-6-luna"):
                    # Integer tenths of a dollar per million tokens.
                    estimated_cost[endpoint] += (row.input_tokens or 0) + (
                        0 if endpoint == "decisions" else 5 * (row.output_tokens or 0)
                    )
    return dict(models), estimated_cost


def _outcome(  # noqa: PLR0913 - Keep benchmark inputs and replay settings explicit.
    *,
    packet: Packet,
    arm: Arm,
    blind: Blind,
    complete: bool,
    status: str,
    started: float,
    workspace: Path,
    failures: tuple[str, ...],
) -> Outcome:
    journals = tuple((workspace / "receipts").glob("*.sqlite3"))
    usage, cost = _recorded_usage(journals)
    write_json(
        path=workspace / "usage.json",
        value={"models": usage, "uncached_cost_tenths_per_million": cost},
    )
    return Outcome(
        packet=packet.id,
        arm=arm,
        blind=blind,
        complete=complete,
        status=status,
        local_sha256=digest(blind=blind),
        failures=failures,
        latency_seconds=monotonic() - started,
        input_tokens=sum(row["input_tokens"] for row in usage.values()),
        output_tokens=sum(row["output_tokens"] for row in usage.values()),
        cost_usd=cost.total() / 10_000_000
        if cost and all(not row["usage_missing"] for row in usage.values())
        else None,
    )


async def run_packet(  # noqa: PLR0913 - Keep benchmark inputs and replay settings explicit.
    *,
    packet: Packet,
    arm: Literal["open", "direct"],
    root: Path,
    workspace: Path,
    provider: ModelGateway,
    pack: ReferencePack | None,
    profile: str = PROFILE,
) -> tuple[Outcome, ...]:
    """Execute one first attempt, producing the late view from the same open draft."""
    started = monotonic()
    derived = workspace / "visible"
    await asyncio.to_thread(derived.mkdir, parents=True, exist_ok=False)
    evidence_root, visible_root = await asyncio.gather(
        asyncio.to_thread(root.resolve), asyncio.to_thread(derived.resolve)
    )
    graph = LangGraphDiscoveryGateway(
        gateway=provider,
        directory=workspace / "receipts",
        profile=profile,
    )
    client = Client(
        config=ClientConfiguration(
            base_dir=workspace / "sdk",
            model_gateway=graph,
            readers=[
                FilesystemReader(name="evidence", root=evidence_root),
                FilesystemReader(name="visible", root=visible_root),
            ],
            parsers=Parsers(documents=DoclingParser()),
            retention=Retention(extracted_text=True),
        )
    )
    project = await client.create_project(name="discovery", actor=ACTOR)
    captures = await _ingest(project=project, packet=packet, root=root, derived=derived)
    if arm == "direct":
        blind, input_tokens, output_tokens, model = await _direct(
            gateway=provider,
            project=project,
            packet=packet,
            captures=captures,
        )
        estimate = (
            (input_tokens + 5 * output_tokens) / 10_000_000
            if input_tokens is not None
            and output_tokens is not None
            and model.removeprefix("openai/").startswith("gpt-6-luna")
            else None
        )
        return (
            Outcome(
                packet=packet.id,
                arm=arm,
                blind=blind,
                complete=True,
                status="needs_review",
                local_sha256=digest(blind=blind),
                latency_seconds=monotonic() - started,
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
                cost_usd=estimate,
            ),
        )

    model = await project.create_model(
        name="observed",
        description=packet.purpose,
        kind=ModelKind.PROPOSED,
        actor=ACTOR,
        reference_pack=pack,
    )
    contexts = tuple(
        DiscoverySourceContext(
            revision=captures[source.id],
            owner=source.publisher,
            role=source.role,
            effective_from=source.effective_from,
            effective_until=source.effective_until,
            supersedes=captures[source.supersedes] if source.supersedes else None,
        )
        for source in packet.sources
    )
    run = await model.discover(
        actor=ACTOR,
        sources=tuple(captures.values()),
        additional_instructions=INSTRUCTIONS,
        idempotency_key="procurement-v23",
        schema_options=SchemaDiscoveryOptions(
            competency_questions=tuple(
                CompetencyQuestion(id=q.id, text=q.text) for q in packet.questions
            ),
            source_context=contexts,
            as_of=packet.published,
        ),
    )
    sources = {revision: name for name, revision in captures.items()}
    blind, ids = await _blind(project=project, model=model, run=run, sources=sources)
    write_json(path=workspace / "local-draft.json", value=blind)
    coverage = await asyncio.gather(
        *(model.get_discovery_coverage(run_id=run.id, source=revision) for revision in sources)
    )
    deferred = tuple(
        f"Deferred coverage: {name}"
        for item, name in zip(coverage, sources.values(), strict=True)
        if item is not None and item.has_deferred
    )
    failures = (*[f"{failure.code}: {failure.message}" for failure in run.failures], *deferred)
    complete = run.status in (RunStatus.NEEDS_REVIEW, RunStatus.READY_TO_PREPARE) and not failures
    outcome = _outcome(
        packet=packet,
        arm=arm,
        blind=blind,
        complete=complete,
        status=run.status.value,
        started=started,
        workspace=workspace,
        failures=failures,
    )
    if pack is None:
        return (outcome,)
    suggestions: tuple[Suggestion, ...] = ()
    if run.reconciliation_id is not None:
        alignment = await model.get_alignment(alignment_id=run.reconciliation_id)
        suggestions = await _mappings(
            alignment=alignment, project=project, blind=blind, ids=ids, sources=sources
        )
    aligned = blind.model_copy(
        update={
            "id": token_hex(12),
            "mappings": suggestions,
        }
    )
    if digest(blind=aligned) != outcome.local_sha256:
        raise ValueError("Reference comparison changed the frozen local review content.")
    # Late and open share inference. Do not double-count the provider receipts.
    return (
        outcome,
        Outcome(
            packet=packet.id,
            arm="late",
            blind=aligned,
            complete=complete,
            status=run.status.value,
            local_sha256=outcome.local_sha256,
            latency_seconds=0.0,
            failures=failures,
        ),
    )
