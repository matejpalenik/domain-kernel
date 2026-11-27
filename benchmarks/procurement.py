"""Prepare, execute and score the real-document EU procurement benchmark."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from time import monotonic
from typing import TYPE_CHECKING, Literal, override

from pydantic import TypeAdapter

from benchmarks.procurement_codex import CODEX_EFFORT, CODEX_PROFILE, CodexProcurementGateway
from benchmarks.procurement_data import (
    DEVELOPMENT_NOTICE,
    PER_STRATUM,
    STRATA,
    WORKSPACE,
    Corpus,
    GraderCapture,
    KeySet,
    PacketKey,
    Question,
    Record,
    capture_path,
    choose_packets,
    validate_capture,
    validate_corpus,
    validate_keys,
    write_json,
)
from benchmarks.procurement_run import (
    ATTEMPTS,
    PROFILE,
    TOKENS,
    WORKFLOW_VERSION,
    partial_pack,
    run_packet,
)
from benchmarks.procurement_score import (
    Blind,
    Campaign,
    Judgments,
    Outcome,
    Submission,
    digest,
    scorecard,
    submission_campaign,
)
from domain_kernel import DomainKernelError, LiteLLMGateway, ModelRequest, ModelResponse
from domain_kernel.discovery.application.errors.truncated_response_error import (
    TruncatedResponseError,
)
from domain_kernel.discovery.application.protocols.model_gateway import ModelGateway
from domain_kernel.discovery.domain.schema_policy import COMPACT_STAGES
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.hashing import Hashing
from examples.notebooks.live_discovery import official_api_key

if TYPE_CHECKING:
    from collections.abc import Sequence

    from benchmarks.procurement_data import Packet, Split
    from domain_kernel.discovery.application.contracts.truncated_response import TruncatedResponse

type RunArm = Literal["open", "direct"]
type Backend = Literal["api", "codex"]


class ProviderCall(Record):
    """Provider cost and latency receipt without document text."""

    stage: str
    request: str
    request_fingerprint: str | None = None
    seconds: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    status: str
    sdk_attempt: int | None = None


@dataclass(frozen=True, kw_only=True)
class MeteredLuna(ModelGateway):
    """Observe the SDK's actual dispatches, including failed attempts."""

    provider: LiteLLMGateway | CodexProcurementGateway
    calls: list[ProviderCall] = field(default_factory=list[ProviderCall], compare=False)

    @property
    def supports_schema_discovery(self) -> bool:
        """Keep the provider's schema discovery contract."""
        return self.provider.supports_schema_discovery

    def input_ceiling(self, *, request: ModelRequest) -> int:
        """Preserve the provider's input accounting for bounded stage requests."""
        return self.provider.input_ceiling(request=request)

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Meter each dispatch without adding retry or transport policy."""
        fingerprint = Hashing.hash_json(
            value=RecordCodec.to_value(
                value=(
                    request.request_id,
                    request.scope,
                    request.instructions,
                    request.context_json,
                    request.response_schema_json,
                    tuple((part.text, part.evidence, part.is_table) for part in request.inputs),
                    request.max_output_tokens,
                    request.use_provider_output_limit,
                )
            )
        ).value
        attempt = None
        if request.provider_stage in COMPACT_STAGES:
            frame = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
            value = frame.get("attempt")
            if type(value) is int:
                attempt = value
        started = monotonic()
        reply: ModelResponse | TruncatedResponse | None = None
        status = "failed"
        try:
            reply = await self.provider.generate(request=request)
        except TruncatedResponseError as error:
            reply = error.response
            status = "truncated"
            raise
        else:
            status = "complete"
            return reply
        finally:
            self.calls.append(
                ProviderCall(
                    stage=request.provider_stage or "unspecified",
                    request=request.request_id,
                    request_fingerprint=fingerprint,
                    seconds=monotonic() - started,
                    input_tokens=reply.input_tokens if reply else None,
                    output_tokens=reply.output_tokens if reply else None,
                    model=reply.model_id if reply else None,
                    status=status,
                    sdk_attempt=attempt,
                )
            )


def _retry_count(*, calls: Sequence[ProviderCall]) -> int:
    failed: set[str] = set()
    retries = 0
    for call in calls:
        if call.sdk_attempt is not None:
            retries += int(call.sdk_attempt > 1)
            continue
        fingerprint = call.request_fingerprint
        if fingerprint is None:
            continue
        retries += int(fingerprint in failed)
        if call.status == "failed":
            failed.add(fingerprint)
        else:
            failed.discard(fingerprint)
    return retries


def _costed(*, outcome: Outcome, calls: Sequence[ProviderCall], backend: Backend) -> Outcome:
    inputs = sum(call.input_tokens or 0 for call in calls)
    outputs = sum(call.output_tokens or 0 for call in calls)
    priced = backend == "api" and all(
        c.input_tokens is not None
        and c.output_tokens is not None
        and c.model is not None
        and c.model.removeprefix("openai/").startswith("gpt-6-luna")
        for c in calls
    )
    provider_seconds = sum(call.seconds for call in calls)
    return outcome.model_copy(
        update={
            "provider_seconds": provider_seconds,
            "latency_seconds": provider_seconds
            if outcome.arm == "late"
            else outcome.latency_seconds,
            "input_tokens": inputs,
            "output_tokens": outputs,
            "cost_usd": (inputs + 5 * outputs) / 10_000_000 if priced else None,
            "retries": _retry_count(calls=calls),
        }
    )


class Options(argparse.Namespace):
    """Explicit benchmark command inputs."""

    command: str = ""
    root: Path = WORKSPACE
    corpus: Path | None = None
    output: Path | None = None
    judgments: Path | None = None
    submission: Path | None = None
    inputs_only: bool = False
    split: Split | None = None
    backend: Backend = "api"


def prepare(*, options: Options) -> None:
    """Select a frozen public corpus and export the private review contract."""
    path = options.corpus or options.root / "candidate-corpus.json"
    candidates = Corpus.model_validate_json(path.read_bytes())
    counts = Counter(p.stratum for p in candidates.packets)
    report = options.root / "preparation.json"
    shortfall = {s: PER_STRATUM - counts[s] for s in STRATA if counts[s] < PER_STRATUM}
    if shortfall:
        write_json(
            path=report,
            value={
                "status": "corpus_shortfall",
                "candidate_packets": len(candidates.packets),
                "by_stratum": dict(counts),
                "missing_by_stratum": shortfall,
            },
        )
        msg = f"Corpus shortfall: {shortfall}. See {report}."
        raise ValueError(msg)
    selected = choose_packets(
        groups={
            stratum: [(p.id, p.group) for p in candidates.packets if p.stratum == stratum]
            for stratum in STRATA
        }
    )
    corpus = candidates.model_copy(
        update={
            "packets": tuple(
                p.model_copy(update={"split": selected[p.id]})
                for p in sorted(candidates.packets, key=lambda row: row.id)
                if p.id in selected
            ),
        }
    )
    validate_corpus(corpus=corpus, root=options.root / "public")
    manifest_path = options.root / "corpus.json"
    if manifest_path.exists() or (options.root / "grader" / "key-for-review.json").exists():
        raise ValueError("Prepare into a new corpus workspace to preserve frozen captures.")
    draft_path = options.root / "grader" / "draft-keys.json"
    drafts = (
        TypeAdapter(dict[str, PacketKey]).validate_json(draft_path.read_bytes())
        if draft_path.is_file()
        else {}
    )
    if any(
        key.packet != packet_id or key.procurement_reviewer or key.ontology_reviewer
        for packet_id, key in drafts.items()
    ):
        raise ValueError("Draft keys must match their packet IDs and carry no reviewer sign-off.")
    write_json(path=manifest_path, value=corpus)
    key = KeySet(
        corpus_sha256=sha256(manifest_path.read_bytes()).hexdigest(),
        packets=tuple(drafts.get(p.id) or PacketKey(packet=p.id) for p in corpus.packets),
    )
    write_json(path=options.root / "grader" / "key-for-review.json", value=key)
    write_json(path=report, value={"status": "awaiting_key_review", "selected": selected})


def _inputs(*, root: Path) -> tuple[Corpus, str]:
    data = (root / "corpus.json").read_bytes()
    corpus = Corpus.model_validate_json(data)
    validate_corpus(corpus=corpus, root=root / "public")
    return corpus, sha256(data).hexdigest()


def _frozen(*, root: Path, split: Split | None = None) -> tuple[Corpus, KeySet, str, str]:
    corpus, corpus_hash = _inputs(root=root)
    private = root / "grader"
    split_key = private / f"reviewed-key-{split}.json" if split else None
    private_key = split_key if split_key and split_key.is_file() else private / "reviewed-key.json"
    if not private_key.is_file():
        raise ValueError(
            "Independent procurement and ontology reviewers must freeze reviewed-key.json."
        )
    raw_key = private_key.read_bytes()
    key = KeySet.model_validate_json(raw_key)
    validate_keys(
        keys=key, corpus=corpus, corpus_sha256=corpus_hash, private_root=private, split=split
    )
    return corpus, key, corpus_hash, sha256(raw_key).hexdigest()


def _ontology(*, root: Path) -> GraderCapture:
    private = root / "grader"
    pin = GraderCapture.model_validate_json((private / "ontology.json").read_bytes())
    if pin.version != "ePO 5.2.0":
        raise ValueError("Use the pinned ePO 5.2.0 core.")
    validate_capture(path=capture_path(root=private, file=pin.file), expected=pin.sha256)
    return pin


def _options() -> Options:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.procurement")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "validate", "run", "smoke", "submit", "score"):
        action = sub.add_parser(command)
        _ = action.add_argument("--root", type=Path, default=WORKSPACE)
        if command == "prepare":
            _ = action.add_argument("--corpus", type=Path)
        if command == "validate":
            _ = action.add_argument("--inputs-only", action="store_true")
            _ = action.add_argument("--split", choices=("development", "locked"))
        if command in ("run", "smoke", "submit", "score"):
            _ = action.add_argument("--output", required=True, type=Path)
        if command == "submit":
            _ = action.add_argument("--submission", required=True, type=Path)
        if command == "run":
            _ = action.add_argument(
                "--split", choices=("development", "locked"), default="development"
            )
            _ = action.add_argument("--backend", choices=("api", "codex"), default="api")
        if command == "score":
            _ = action.add_argument("--judgments", type=Path)
    return parser.parse_args(namespace=Options())


def _failed(*, packet: Packet, arm: RunArm, detail: str, started: float) -> tuple[Outcome, ...]:
    blind = Blind(id=token_hex(12))
    outcome = Outcome(
        packet=packet.id,
        arm=arm,
        complete=False,
        status="failed",
        blind=blind,
        local_sha256=digest(blind=blind),
        latency_seconds=monotonic() - started,
        failures=(detail,),
    )
    if arm != "open":
        return (outcome,)
    return (
        outcome,
        outcome.model_copy(
            update={"arm": "late", "blind": Blind(id=token_hex(12)), "latency_seconds": 0.0}
        ),
    )


async def _run(*, options: Options, output: Path) -> None:
    split = options.split or "development"
    corpus, _, public_hash, key_hash = _frozen(root=options.root, split=split)
    ontology = _ontology(root=options.root)
    pack = partial_pack(ontology=capture_path(root=options.root / "grader", file=ontology.file))
    provider = MeteredLuna(
        provider=(
            CodexProcurementGateway()
            if options.backend == "codex"
            else LiteLLMGateway(
                api_key=official_api_key(), reasoning_effort=CODEX_EFFORT, max_output_tokens=TOKENS
            )
        )
    )
    profile = CODEX_PROFILE if options.backend == "codex" else PROFILE
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=False)
    await asyncio.to_thread((output / "blind").mkdir)
    write_json(
        path=output / "protocol.json",
        value={
            "backend": options.backend,
            "profile": profile,
            "model": provider.provider.model,
            "reasoning_effort": CODEX_EFFORT,
            "provider_output_tokens": TOKENS if options.backend == "api" else None,
            "stage_attempts": ATTEMPTS,
            "runner_retries": 0,
            "review_cap": 128,
            "workflow": WORKFLOW_VERSION,
            "ontology": ontology.model_dump(mode="json"),
            "reference_pack_sha256": pack.pin.content_hash.value,
        },
    )
    index = Campaign(corpus_sha256=public_hash, keys_sha256=key_hash, split=split)
    write_json(path=output / "private-index.json", value=index)
    results: list[Outcome] = []
    for packet in corpus.packets:
        if packet.split != split:
            continue
        for arm in ("open", "direct"):
            started = monotonic()
            provider.calls.clear()
            location = output / "cases" / packet.id / arm
            try:
                batch = await run_packet(
                    packet=packet,
                    arm=arm,
                    root=options.root / "public",
                    provider=provider,
                    pack=pack,
                    profile=profile,
                    workspace=location,
                )
            except (DomainKernelError, OSError, ValueError) as exc:
                batch = _failed(packet=packet, arm=arm, detail=str(exc), started=started)
            write_json(
                path=location / "provider-calls.json",
                value=[call.model_dump(mode="json") for call in provider.calls],
            )
            batch = tuple(
                _costed(
                    outcome=row,
                    backend=options.backend,
                    calls=tuple(
                        c
                        for c in provider.calls
                        if arm != "open" or (c.stage == "schema-mapping") == (row.arm == "late")
                    ),
                )
                for row in batch
            )
            results.extend(batch)
            for outcome in batch:
                _write_blind(directory=output / "blind", packet=packet, blind=outcome.blind)
            write_json(
                path=output / "private-index.json",
                value=index.model_copy(update={"outcomes": tuple(results)}),
            )


async def _smoke(*, root: Path, output: Path) -> None:
    corpus, manifest_hash = _inputs(root=root)
    original = next(p for p in corpus.packets if p.id == DEVELOPMENT_NOTICE)
    source = original.sources[0].model_copy(update={"pages": (5,)})
    packet = original.model_copy(
        update={
            "purpose": "Model how a lot is linked to a reported award outcome.",
            "questions": (
                Question(
                    id="CQ-smoke",
                    text="How do we represent a lot that closed without a winner?",
                ),
            ),
            "sources": (source,),
        }
    )
    provider = MeteredLuna(provider=CodexProcurementGateway())
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=False)
    write_json(
        path=output / "protocol.json",
        value={
            "purpose": "technical smoke",
            "backend": "codex",
            "profile": CODEX_PROFILE,
            "model": provider.provider.model,
            "reasoning_effort": CODEX_EFFORT,
            "workflow": WORKFLOW_VERSION,
            "corpus_sha256": manifest_hash,
            "packet": packet.id,
            "source": source.model_dump(mode="json"),
            "stage_attempts": ATTEMPTS,
            "runner_retries": 0,
            "review_cap": 128,
        },
    )
    started = monotonic()
    try:
        (outcome,) = await run_packet(
            packet=packet,
            arm="open",
            root=root / "public",
            workspace=output / "case",
            provider=provider,
            pack=None,
            profile=CODEX_PROFILE,
        )
    except (DomainKernelError, OSError, ValueError) as error:
        outcome = _failed(packet=packet, arm="open", detail=str(error), started=started)[0]
    write_json(
        path=output / "provider-calls.json",
        value=[call.model_dump(mode="json") for call in provider.calls],
    )
    measured = _costed(outcome=outcome, calls=provider.calls, backend="codex")
    write_json(path=output / "result.json", value=measured)
    if not measured.complete or not measured.blind.proposals:
        raise ValueError(
            "The Codex smoke did not produce a complete review draft. See result.json."
        )


def _write_blind(*, directory: Path, packet: Packet, blind: Blind) -> None:
    write_json(
        path=directory / f"{blind.id}.json",
        value={
            "scenario": packet.purpose,
            "questions": [q.model_dump(mode="json") for q in packet.questions],
            "sources": [s.model_dump(mode="json") for s in packet.sources],
            **blind.model_dump(mode="json"),
        },
    )


def _submit(*, root: Path, output: Path, source: Path) -> None:
    submission = Submission.model_validate_json(source.read_bytes())
    corpus, _, public_hash, key_hash = _frozen(root=root, split=submission.split)
    if submission.corpus_sha256 != public_hash:
        raise ValueError("Submit against the exact public corpus manifest.")
    campaign = submission_campaign(submission=submission, corpus=corpus, keys_sha256=key_hash)
    packets = {packet.id: packet for packet in corpus.packets}
    output.mkdir(parents=True, exist_ok=False)
    for outcome in campaign.outcomes:
        _write_blind(
            directory=output / "blind", packet=packets[outcome.packet], blind=outcome.blind
        )
    write_json(path=output / "private-index.json", value=campaign)


def _score(*, options: Options, output: Path) -> None:
    campaign = Campaign.model_validate_json((output / "private-index.json").read_bytes())
    corpus, keys, public_hash, key_hash = _frozen(root=options.root, split=campaign.split)
    if campaign.corpus_sha256 != public_hash or campaign.keys_sha256 != key_hash:
        raise ValueError("Run artifacts require their original public manifest and private key.")
    judgments = (
        Judgments.model_validate_json(options.judgments.read_bytes())
        if options.judgments is not None
        else Judgments(packets=())
    )
    report = scorecard(corpus=corpus, keys=keys, campaign=campaign, judgments=judgments)
    write_json(path=output / "scorecard.json", value=report)


def main() -> None:
    """Dispatch an explicit campaign command."""
    options = _options()
    if options.command == "prepare":
        prepare(options=options)
    elif options.command == "validate":
        _ = (
            _inputs(root=options.root)
            if options.inputs_only
            else _frozen(root=options.root, split=options.split)
        )
        _ = _ontology(root=options.root)
    elif options.output is None:
        raise ValueError("Select a campaign output directory.")
    elif options.command == "run":
        asyncio.run(_run(options=options, output=options.output))
    elif options.command == "smoke":
        asyncio.run(_smoke(root=options.root, output=options.output))
    elif options.command == "submit" and options.submission is not None:
        _submit(root=options.root, output=options.output, source=options.submission)
    elif options.command == "score":
        _score(options=options, output=options.output)


if __name__ == "__main__":
    main()
