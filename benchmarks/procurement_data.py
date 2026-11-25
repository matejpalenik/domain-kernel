"""Prepare and validate the public inputs and private keys for procurement discovery."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from random import Random
from typing import ClassVar, Literal, override

from pydantic import BaseModel, ConfigDict

from domain_kernel.discovery.infrastructure.checkpoints import write_private

EPO = "https://github.com/OP-TED/ePO/tree/v5.2.0"
NAMESPACE = "http://data.europa.eu/a4g/ontology#"
WORKSPACE = Path(__file__).resolve().parents[1] / "local/benchmarks/procurement"
STRATA = ("single", "linked", "buyer")
SEED = 42
PER_STRATUM = 8
DEVELOPMENT_PER_STRATUM = 2
MIN_QUESTIONS = 2
MAX_QUESTIONS = 4
MIN_LINKED_NOTICES = 2
DEVELOPMENT_NOTICE = "ted-446635-2025"

type Stratum = Literal["single", "linked", "buyer"]
type Split = Literal["development", "locked"]
type Format = Literal["pdf", "html", "docx", "xlsx", "csv"]
type SourceRole = Literal["policy", "observed_practice", "template", "reference", "unknown"]
type Kind = Literal["concept", "relationship", "rule"]


class Record(BaseModel):
    """Strict artifact schema."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class Source(Record):
    """Exact public bytes supplied to the parser."""

    id: str
    file: str
    sha256: str
    url: str
    publisher: str
    format: Format
    role: SourceRole = "unknown"
    effective_from: date | None = None
    effective_until: date | None = None
    supersedes: str | None = None
    publication: str | None = None
    language: Literal["en"] = "en"
    reuse: str
    pages: tuple[int, ...] = ()


class Question(Record):
    """Business question sent to inference."""

    id: str
    text: str


class Packet(Record):
    """One independently selected procurement procedure and its evidence."""

    id: str
    procedure: str
    buyer: str
    group: str
    stratum: Stratum
    split: Split | None = None
    published: date
    purpose: str
    questions: tuple[Question, ...]
    sources: tuple[Source, ...]


class Corpus(Record):
    """Public inputs only, without any grading material."""

    version: Literal["1"] = "1"
    ontology: Literal["ePO 5.2.0"] = "ePO 5.2.0"
    seed: Literal[42] = SEED
    packets: tuple[Packet, ...]


class EvidenceKey(Record):
    """Expected text and its human-checkable pointer in the source."""

    source: str
    locator: str
    quote: str


class Target(Record):
    """A meaning and its status in this packet."""

    id: str
    question: str
    kind: Kind
    meaning: str
    disposition: Literal["required", "optional", "unobservable", "forbidden", "clarification"]
    evidence: tuple[EvidenceKey, ...] = ()
    iri: str | None = None
    roles: tuple[str, str] | None = None
    scope: str = ""
    alternatives: tuple[str, ...] = ()


class Slot(Record):
    """A typed reference to a reviewed definition used by a fixture."""

    name: str
    kind: Kind
    target: str
    endpoints: tuple[str, str] | None = None


class Fixture(Record):
    """A predeclared executable competency or constraint check."""

    id: str
    question: str
    modelet: str
    slots: tuple[Slot, ...]
    graph: str
    query: str | None = None
    expected: tuple[tuple[str, ...], ...] | bool
    shape: str | None = None
    critical: bool = False
    alternative_group: str | None = None


class MappingTarget(Record):
    """An ePO meaning and the allowed mapping relation."""

    target: str
    iri: str
    relation: Literal["equivalent", "broader", "narrower", "related"]
    seeded: bool


class GraderCapture(Record):
    """A separately acquired structured cross-check or ontology file."""

    file: str
    sha256: str
    url: str
    version: str


class PacketKey(Record):
    """Private reviewed key, cross-check provenance and executable fixtures."""

    packet: str
    procurement_reviewer: str = ""
    ontology_reviewer: str = ""
    authority_notes: tuple[str, ...] = ()
    cross_checks: tuple[GraderCapture, ...] = ()
    mapping_version: str = ""
    targets: tuple[Target, ...] = ()
    mappings: tuple[MappingTarget, ...] = ()
    fixtures: tuple[Fixture, ...] = ()


class KeySet(Record):
    """Private keys bound to the exact public manifest."""

    corpus_sha256: str
    packets: tuple[PacketKey, ...]


def write_json(*, path: Path, value: object) -> None:
    """Persist JSON using the benchmark's private artifact permissions."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    write_private(
        path=path, payload=(json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    )


def validate_capture(*, path: Path, expected: str) -> None:
    """Reject missing or changed evidence."""
    if not path.is_file():
        msg = f"Source capture missing: {path}"
        raise ValueError(msg)
    if sha256(path.read_bytes()).hexdigest() != expected:
        msg = f"Source capture hash differs: {path}"
        raise ValueError(msg)


def capture_path(*, root: Path, file: str) -> Path:
    """Resolve a capture only beneath its assigned evidence directory."""
    path = (root / file).resolve()
    if not path.is_relative_to(root.resolve()) or Path(file).is_absolute():
        raise ValueError("Source files must be relative to the capture root.")
    return path


def choose_packets(
    *, groups: dict[str, list[tuple[str, str]]], required_development: str = DEVELOPMENT_NOTICE
) -> dict[str, str]:
    """Select 24 procedures with two development cases per stratum."""
    if set(groups) != set(STRATA):
        raise ValueError("Use all three procurement strata.")
    ids = [case for rows in groups.values() for case, _ in rows]
    group_ids = [group for rows in groups.values() for _, group in rows]
    if len(ids) != len(set(ids)) or len(group_ids) != len(set(group_ids)):
        raise ValueError("Select at most one packet per independent group.")
    if required_development not in ids:
        raise ValueError("Include the documented development notice.")
    rng = Random(SEED)  # noqa: S311 -- Reproducible benchmark sampling.
    selected: dict[str, str] = {}
    for stratum in STRATA:
        ordered = sorted(case for case, _ in groups[stratum])
        rng.shuffle(ordered)
        if required_development in ordered:
            ordered.remove(required_development)
            ordered.insert(0, required_development)
        if len(ordered) < PER_STRATUM:
            msg = f"Corpus shortfall in {stratum}: {len(ordered)}/8."
            raise ValueError(msg)
        selected.update(
            {
                case: "development" if i < DEVELOPMENT_PER_STRATUM else "locked"
                for i, case in enumerate(ordered[:PER_STRATUM])
            }
        )
    return selected


def validate_corpus(*, corpus: Corpus, root: Path) -> None:  # noqa: C901 -- Enforce corpus and evidence isolation together.
    """Verify sample isolation, payload roles, and original bytes offline."""
    counts = Counter((p.stratum, p.split) for p in corpus.packets)
    if counts != Counter(
        {(s, split): n for s in STRATA for split, n in (("development", 2), ("locked", 6))}
    ):
        raise ValueError("Require two development and six locked packets per stratum.")
    if not any(p.id == DEVELOPMENT_NOTICE and p.split == "development" for p in corpus.packets):
        raise ValueError("Keep the published worked example in development.")
    for field in ("id", "procedure", "buyer", "group"):
        if len({getattr(p, field) for p in corpus.packets}) != len(corpus.packets):
            msg = f"Duplicate {field} across independent procurement packets."
            raise ValueError(msg)
    digests: set[str] = set()
    notices: set[str] = set()
    for packet in corpus.packets:
        if (
            not date(2024, 1, 1) <= packet.published <= date(2026, 10, 31)
            or not re.fullmatch(r"[a-z0-9-]+", packet.id)
            or not packet.procedure.strip()
            or not packet.buyer.strip()
            or not packet.group.strip()
            or not packet.purpose.strip()
        ):
            msg = f"Invalid packet identity, date or scope: {packet.id}"
            raise ValueError(msg)
        questions = {q.id for q in packet.questions if q.text.strip() and q.id.strip()}
        if not MIN_QUESTIONS <= len(packet.questions) <= MAX_QUESTIONS or len(questions) != len(
            packet.questions
        ):
            msg = f"Require two to four unique competency questions: {packet.id}"
            raise ValueError(msg)
        publications = {s.publication for s in packet.sources if s.publication}
        attachments = [s for s in packet.sources if not s.publication]
        if (
            (packet.stratum == "single" and (len(publications) != 1 or attachments))
            or (
                packet.stratum == "linked"
                and (len(publications) < MIN_LINKED_NOTICES or attachments)
            )
            or (packet.stratum == "buyer" and (not publications or not attachments))
            or bool(notices & publications)
        ):
            msg = f"Wrong source mix or repeated publication: {packet.id}"
            raise ValueError(msg)
        sources = {s.id: s for s in packet.sources}
        if len(sources) != len(packet.sources):
            msg = f"Repeated source ID: {packet.id}"
            raise ValueError(msg)
        local_digests: set[str] = set()
        for source in packet.sources:
            if (
                not source.id.strip()
                or not source.publisher.strip()
                or not source.reuse.strip()
                or not source.url.startswith("https://")
                or (
                    source.pages
                    and (
                        source.format != "pdf"
                        or tuple(sorted(set(source.pages))) != source.pages
                        or min(source.pages) < 1
                    )
                )
                or source.sha256 in digests
                or source.sha256 in local_digests
                or (
                    source.supersedes is not None
                    and (source.supersedes not in sources or source.supersedes == source.id)
                )
            ):
                msg = f"Unverified or repeated source: {packet.id}/{source.id}"
                raise ValueError(msg)
            path = capture_path(root=root, file=source.file)
            validate_capture(path=path, expected=source.sha256)
            local_digests.add(source.sha256)
        notices.update(publications)
        digests.update(local_digests)


def validate_keys(
    *,
    keys: KeySet,
    corpus: Corpus,
    corpus_sha256: str,
    private_root: Path,
    split: Split | None = None,
) -> None:
    """Bind independent reviewed keys to the corpus without exposing their contents."""
    by_packet = {key.packet: key for key in keys.packets}
    selected = tuple(p for p in corpus.packets if split is None or p.split == split)
    required_ids = {packet.id for packet in selected}
    if (
        keys.corpus_sha256 != corpus_sha256
        or len(by_packet) != len(keys.packets)
        or not required_ids <= by_packet.keys()
        or not by_packet.keys() <= {packet.id for packet in corpus.packets}
    ):
        raise ValueError("Use the reviewed keys for the exact frozen manifest.")
    for packet in selected:
        key = by_packet[packet.id]
        if (
            not key.procurement_reviewer.strip()
            or not key.ontology_reviewer.strip()
            or key.procurement_reviewer.strip().casefold()
            == key.ontology_reviewer.strip().casefold()
            or not key.mapping_version.strip()
            or not key.cross_checks
        ):
            msg = f"Independent reviewed key and cross-check required: {packet.id}"
            raise ValueError(msg)
        for source in key.cross_checks:
            validate_capture(
                path=capture_path(root=private_root, file=source.file), expected=source.sha256
            )
        _validate_targets(packet=packet, key=key)


def _validate_targets(*, packet: Packet, key: PacketKey) -> None:
    questions = {question.id for question in packet.questions}
    targets = {target.id: target for target in key.targets}
    source_ids = {source.id for source in packet.sources}
    fixtures = {fixture.id for fixture in key.fixtures}
    required = {target.question for target in key.targets if target.disposition == "required"}
    if (
        len(targets) != len(key.targets)
        or len(fixtures) != len(key.fixtures)
        or required != questions
        or {item.question for item in key.fixtures} != questions
        or not any(item.critical for item in key.fixtures)
        or not any(item.expected is False or item.expected == () for item in key.fixtures)
    ):
        msg = f"Each question needs a required meaning and fixture: {packet.id}"
        raise ValueError(msg)
    for target in key.targets:
        if (
            target.question not in questions
            or not target.meaning.strip()
            or (target.kind == "relationship" and target.roles is None)
            or (target.disposition in ("required", "clarification") and not target.evidence)
            or (target.disposition == "clarification" and not target.scope.strip())
            or any(
                e.source not in source_ids or not e.quote or not e.locator for e in target.evidence
            )
        ):
            msg = f"Invalid target scope or evidence: {packet.id}/{target.id}"
            raise ValueError(msg)
    if len({(m.target, m.iri, m.relation) for m in key.mappings}) != len(key.mappings):
        msg = f"Repeated reference mapping: {packet.id}"
        raise ValueError(msg)
    for mapping in key.mappings:
        if mapping.target not in targets or not mapping.iri:
            msg = f"Use a keyed meaning and pinned mapping: {packet.id}"
            raise ValueError(msg)
    _validate_fixtures(key=key, targets=targets)


def _validate_fixtures(*, key: PacketKey, targets: dict[str, Target]) -> None:
    groups: dict[str, tuple[str, bool]] = {}
    for fixture in key.fixtures:
        if fixture.alternative_group is not None:
            policy = (fixture.question, fixture.critical)
            if groups.setdefault(fixture.alternative_group, policy) != policy:
                raise ValueError("Fixture alternatives must share a question and criticality.")
        slots = {slot.name: slot for slot in fixture.slots}
        if (
            not slots
            or len(slots) != len(fixture.slots)
            or any(
                slot.target not in targets or targets[slot.target].kind != slot.kind
                for slot in fixture.slots
            )
            or any(
                (slot.kind == "relationship") != (slot.endpoints is not None)
                for slot in slots.values()
            )
            or any(
                slot.endpoints
                and any(
                    name not in slots or slots[name].kind != "concept" for name in slot.endpoints
                )
                for slot in fixture.slots
            )
            or (fixture.query is None) == (fixture.shape is None)
        ):
            msg = f"Invalid functional fixture: {key.packet}/{fixture.id}"
            raise ValueError(msg)


class _VisibleHTML(HTMLParser):
    """Retain display content and table relationships without machine metadata."""

    _excluded: ClassVar[frozenset[str]] = frozenset(
        ("head", "script", "style", "template", "link", "meta", "noscript", "iframe")
    )
    _void: ClassVar[frozenset[str]] = frozenset(
        (
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "source",
            "track",
            "wbr",
        )
    )
    _attrs: ClassVar[frozenset[str]] = frozenset(("colspan", "rowspan", "scope", "lang"))

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.hidden: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        conceal = any(
            key == "hidden"
            or (key == "aria-hidden" and value == "true")
            or (
                key == "style"
                and value is not None
                and (
                    "display:none" in re.sub(r"\s+", "", value.lower())
                    or "visibility:hidden" in re.sub(r"\s+", "", value.lower())
                )
            )
            for key, value in attrs
        )
        if self.hidden or tag in self._excluded or conceal:
            if tag not in self._void:
                self.hidden.append(tag)
            return
        attributes = "".join(
            f' {k}="{escape(v, quote=True)}"' for k, v in attrs if k in self._attrs and v
        )
        self.output.append(f"<{tag}{attributes}>")

    @override
    def handle_endtag(self, tag: str) -> None:
        if self.hidden:
            if tag in self.hidden:
                position = len(self.hidden) - 1 - self.hidden[::-1].index(tag)
                del self.hidden[position:]
        elif tag not in self._excluded and tag not in self._void:
            self.output.append(f"</{tag}>")

    @override
    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._void:
            self.handle_endtag(tag)

    @override
    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.output.append(escape(data, quote=False))


def visible_html(*, content: bytes) -> bytes:
    """Create the deterministic, parser-visible derivative of a pinned HTML capture."""
    parser = _VisibleHTML()
    parser.feed(content.decode("utf-8-sig"))
    parser.close()
    return "".join(parser.output).encode()
