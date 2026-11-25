"""Score independently reviewed procurement proposals and executable fixtures."""

from __future__ import annotations

import re
from collections import Counter
from hashlib import sha256
from random import Random
from secrets import token_hex
from statistics import mean
from typing import TYPE_CHECKING, Literal
from urllib.parse import quote

from benchmarks.procurement_data import STRATA, Record

if TYPE_CHECKING:
    from rdflib import Graph

    from benchmarks.procurement_data import Corpus, Fixture, KeySet, PacketKey

type Verdict = Literal["match", "extension", "duplicate", "case_specific", "unsupported"]
type Relation = Literal["equivalent", "narrower", "broader", "related"]
type Arm = Literal["open", "late", "guided", "direct", "default-cap", "external"]
ARMS: tuple[Arm, ...] = ("open", "late", "guided", "direct")
MIN_PRECISION = 0.90
MIN_RECALL = 0.80
MIN_SEEDED_COVERAGE = 0.80
MIN_BOOTSTRAP_GROUPS = 2
NO_OPTIONAL_TARGETS: frozenset[str] = frozenset()


class Anchor(Record):
    """A source quote at a readable location."""

    source: str
    revision: str
    locator: str
    quote: str


class ProposedRule(Record):
    """Portable count requirement attached to the discovered model."""

    focus: str
    relationship: str
    minimum: int | None = None
    maximum: int | None = None
    applicable_class: str | None = None
    attribute: str | None = None
    value: str | int | bool | None = None


class Proposal(Record):
    """A blinded, reviewable schema definition."""

    id: str
    title: str
    meaning: str
    kind: Literal["concept", "relationship", "rule"]
    source: str | None = None
    target: str | None = None
    evidence: tuple[Anchor, ...] = ()
    conditions: tuple[str, ...] = ()
    rule: ProposedRule | None = None


class Suggestion(Record):
    """One optional, source-linked mapping for expert review."""

    id: str
    proposal: str
    iri: str
    suggestion: str
    relation: Relation | None = None
    evidence: tuple[Anchor, ...] = ()


class Blind(Record):
    """Review input with no arm or provider identifiers."""

    id: str
    proposals: tuple[Proposal, ...] = ()
    clarifications: tuple[str, ...] = ()
    mappings: tuple[Suggestion, ...] = ()


class Outcome(Record):
    """Private run index record."""

    packet: str
    arm: Arm
    complete: bool
    status: str
    blind: Blind
    local_sha256: str
    latency_seconds: float
    provider_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0
    cost_usd: float | None = None
    failures: tuple[str, ...] = ()


class Campaign(Record):
    """Private replay index for one frozen split."""

    corpus_sha256: str
    keys_sha256: str
    split: Literal["development", "locked"]
    protocol: Literal["sdk", "external"] = "sdk"
    outcomes: tuple[Outcome, ...] = ()


class SubmittedPacket(Record):
    """One pipeline output before benchmark adjudication."""

    packet: str
    proposals: tuple[Proposal, ...] = ()
    clarifications: tuple[str, ...] = ()
    mappings: tuple[Suggestion, ...] = ()
    complete: bool = True


class Submission(Record):
    """Portable exchange format for one pipeline on the frozen inputs."""

    version: Literal["1"] = "1"
    corpus_sha256: str
    split: Literal["development", "locked"]
    packets: tuple[SubmittedPacket, ...]


def submission_campaign(*, submission: Submission, corpus: Corpus, keys_sha256: str) -> Campaign:
    """Wrap external outputs in the same campaign used for blinded scoring."""
    packets = {packet.id: packet for packet in corpus.packets if packet.split == submission.split}
    provided = {row.packet: row for row in submission.packets}
    if (
        not provided
        or len(provided) != len(submission.packets)
        or not provided.keys() <= packets.keys()
    ):
        raise ValueError("Submit distinct packet IDs from the declared split.")
    outcomes: list[Outcome] = []
    for row in submission.packets:
        proposal_ids = {p.id for p in row.proposals if p.id.strip()}
        if len(proposal_ids) != len(row.proposals):
            raise ValueError("Use a distinct nonempty ID for each submitted definition.")
        if len({m.id for m in row.mappings}) != len(row.mappings) or any(
            m.proposal not in proposal_ids for m in row.mappings
        ):
            raise ValueError("Use distinct mappings attached to a submitted definition.")
        revisions = {s.id: f"sha256:{s.sha256}" for s in packets[row.packet].sources}
        if any(
            revisions.get(anchor.source) != anchor.revision
            or not anchor.locator.strip()
            or not anchor.quote.strip()
            for item in (*row.proposals, *row.mappings)
            for anchor in item.evidence
        ):
            raise ValueError("Cite published packet sources with a hash, locator, and quote.")
        blind = Blind(
            id=token_hex(12),
            proposals=row.proposals,
            clarifications=row.clarifications,
            mappings=row.mappings,
        )
        outcomes.append(
            Outcome(
                packet=row.packet,
                arm="external",
                complete=row.complete,
                status="complete" if row.complete else "partial",
                blind=blind,
                local_sha256=digest(blind=blind),
                latency_seconds=0.0,
            )
        )
    return Campaign(
        corpus_sha256=submission.corpus_sha256,
        keys_sha256=keys_sha256,
        split=submission.split,
        protocol="external",
        outcomes=tuple(outcomes),
    )


class Grade(Record):
    """Expert judgment on a single proposal."""

    proposal: str
    verdict: Verdict
    target: str | None = None
    unsupported_bound: bool = False
    lost_critical_condition: bool = False
    reason: str = ""


class MappingGrade(Record):
    """Judge the relation that the system actually suggested."""

    suggestion: str
    relation: Relation | None = None
    correct: bool
    target: str | None = None


class ClarificationGrade(Record):
    """Judgment on one emitted question or specific uncertainty."""

    index: int
    verdict: Literal["match", "extension", "unnecessary", "duplicate"]
    target: str | None = None
    reason: str = ""


class CheckBinding(Record):
    """Bind only existing, reviewed definitions to fixture slots."""

    fixture: str
    slots: dict[str, str]


class Review(Record):
    """One independent review for the issued blind packet."""

    reviewer: str
    grades: tuple[Grade, ...]
    mappings: tuple[MappingGrade, ...] = ()
    checks: tuple[CheckBinding, ...] = ()
    clarifications: tuple[ClarificationGrade, ...] = ()
    corrections: tuple[str, ...] = ()


class Judgment(Record):
    """Retain two primary judgments and a third resolution when they differ."""

    blind_id: str
    first: Review
    second: Review
    adjudication: Review | None = None


class Judgments(Record):
    """Signed review file keyed by blind output identifiers."""

    packets: tuple[Judgment, ...]


def tally(
    *,
    review: Review,
    proposals: set[str],
    required: set[str],
    optional: frozenset[str] = NO_OPTIONAL_TARGETS,
) -> Counter[str]:
    """Apply one-to-one observable credit and keep both denominators."""
    rows = {item.proposal: item for item in review.grades}
    if len(rows) != len(review.grades) or rows.keys() != proposals:
        raise ValueError("Every issued proposal needs exactly one judgment.")
    claimed = set[str]()
    counts: Counter[str] = Counter(proposals=len(proposals), required=len(required))
    for item in rows.values():
        if item.verdict == "match" or (item.verdict == "extension" and item.target is not None):
            allowed = required if item.verdict == "match" else optional
            if item.target is None or item.target not in allowed or item.target in claimed:
                raise ValueError("Use one-to-one matches to keyed observable meanings.")
            claimed.add(item.target)
        elif item.target is not None:
            raise ValueError("Only observed meanings can be assigned targets.")
        counts[item.verdict] += 1
        credited = (
            item.verdict in ("match", "extension")
            and not item.unsupported_bound
            and not item.lost_critical_condition
        )
        counts["correct"] += int(credited)
        counts["recovered"] += int(credited and item.verdict == "match")
        counts["unsupported_bounds"] += int(item.unsupported_bound)
        counts["lost_conditions"] += int(item.lost_critical_condition)
    return counts


def digest(*, blind: Blind) -> str:
    """Hash only the local review content before attaching reference suggestions."""
    return sha256(blind.model_dump_json(exclude={"id", "mappings"}).encode()).hexdigest()


def _signature(review: Review) -> tuple[object, ...]:
    return (
        sorted(
            (g.proposal, g.verdict, g.target, g.unsupported_bound, g.lost_critical_condition)
            for g in review.grades
        ),
        sorted((m.suggestion, m.relation, m.correct, m.target) for m in review.mappings),
        sorted((c.fixture, sorted(c.slots.items())) for c in review.checks),
        sorted((g.index, g.verdict, g.target or "") for g in review.clarifications),
    )


def select_review(*, judgment: Judgment) -> Review:
    """Select an independent adjudication without losing the original votes."""
    first, second, resolved = judgment.first, judgment.second, judgment.adjudication
    identities = [r.reviewer.strip().casefold() for r in (first, second, resolved) if r is not None]
    if "" in identities or len(set(identities)) != len(identities):
        raise ValueError("Supply distinct independent reviewers and adjudicator.")
    if _signature(first) == _signature(second):
        return first
    if resolved is None:
        raise ValueError("Independent judgments disagree and need third-party adjudication.")
    return resolved


def _iri(identity: str) -> str:
    return f"urn:dk:procurement:{quote(identity, safe='')}"


def _render(template: str, values: dict[str, str]) -> str:
    if not set(re.findall(r"\{\{([a-z][a-z0-9_-]*)\}\}", template)) <= values.keys():
        raise ValueError("Executable fixture uses an unbound slot.")
    rendered = re.sub(r"\{\{([a-z][a-z0-9_-]*)\}\}", lambda m: f"<{_iri(values[m[1]])}>", template)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("Invalid fixture substitution.")
    return rendered


def fixture_passes(  # noqa: PLR0911 -- Preserve distinct graph and query outcomes.
    *, fixture: Fixture, binding: CheckBinding, review: Review, blind: Blind
) -> bool:
    """Execute one frozen example against existing, semantically reviewed definitions."""
    from rdflib import Graph  # noqa: PLC0415 -- Optional ontology extra.

    proposed = {p.id: p for p in blind.proposals}
    matched = {
        g.proposal: g.target
        for g in review.grades
        if g.verdict in ("match", "extension")
        and not g.unsupported_bound
        and not g.lost_critical_condition
    }
    slots = {slot.name: slot for slot in fixture.slots}
    if set(binding.slots) != slots.keys():
        return False
    for name, identity in binding.slots.items():
        slot = slots[name]
        row = proposed.get(identity)
        if row is None or row.kind != slot.kind or matched.get(identity) != slot.target:
            return False
        if slot.endpoints and (row.source, row.target) != tuple(
            binding.slots[s] for s in slot.endpoints
        ):
            return False

    graph = Graph().parse(data=_render(fixture.graph, binding.slots), format="turtle")
    if fixture.query is not None:
        query = _render(fixture.query, binding.slots)
        if re.search(r"\b(SERVICE|FROM)\b", query, flags=re.IGNORECASE):
            raise ValueError("Competency queries may only inspect the local graph.")
        result = graph.query(query)
        if isinstance(fixture.expected, bool):
            return result.type == "ASK" and bool(result.askAnswer) == fixture.expected
        if result.type != "SELECT":
            return False
        actual = sorted(
            tuple(str(value) for value in row) for row in result if isinstance(row, tuple)
        )
        return actual == sorted(fixture.expected)
    if fixture.shape is None or not isinstance(fixture.expected, bool):
        raise ValueError("A shape fixture requires an expected validation result.")
    return _shape_passes(fixture=fixture, graph=graph, bindings=binding.slots, proposed=proposed)


def _shape_passes(
    *, fixture: Fixture, graph: Graph, bindings: dict[str, str], proposed: dict[str, Proposal]
) -> bool:
    """Run SHACL on bounds supplied by the candidate's portable rule."""
    from rdflib import BNode, Graph, Literal, Namespace, URIRef  # noqa: PLC0415 -- Optional ontology extra.
    from rdflib.collection import Collection  # noqa: PLC0415 -- Optional ontology extra.
    from rdflib.namespace import RDF  # noqa: PLC0415 -- Optional ontology extra.

    sh = Namespace("http://www.w3.org/ns/shacl#")
    rules = [proposed[bindings[slot.name]].rule for slot in fixture.slots if slot.kind == "rule"]
    if len(rules) != 1 or (rule := rules[0]) is None:
        return False
    relation = proposed.get(rule.relationship)
    if (
        relation is None
        or relation.source != rule.focus
        or relation.target is None
        or rule.relationship not in bindings.values()
        or rule.focus not in bindings.values()
        or relation.target not in bindings.values()
        or (rule.applicable_class and rule.applicable_class not in bindings.values())
        or (rule.minimum is None and rule.maximum is None)
    ):
        return False

    actual = Graph()
    rule_uri = URIRef(
        _iri(next(bindings[slot.name] for slot in fixture.slots if slot.kind == "rule"))
    )
    requirement = URIRef(f"{rule_uri}:requirement")
    property_shape = URIRef(f"{rule_uri}:property")
    _ = actual.add((rule_uri, RDF.type, sh.NodeShape))
    _ = actual.add((rule_uri, sh.targetClass, URIRef(_iri(rule.applicable_class or rule.focus))))
    if rule.attribute is not None and rule.value is not None:
        trigger = BNode()
        trigger_property = BNode()
        outside = BNode()
        choices = BNode()
        _ = actual.add((rule_uri, sh["or"], choices))
        _ = Collection(actual, choices, [outside, requirement])
        _ = actual.add((outside, sh["not"], trigger))
        _ = actual.add((trigger, sh.property, trigger_property))
        _ = actual.add((trigger_property, sh.path, URIRef(_iri(rule.attribute))))
        _ = actual.add((trigger_property, sh.hasValue, Literal(rule.value)))
    else:
        requirement = rule_uri

    _ = actual.add((requirement, sh.property, property_shape))
    _ = actual.add((property_shape, sh.path, URIRef(_iri(rule.relationship))))
    _ = actual.add((property_shape, sh["class"], URIRef(_iri(relation.target))))
    for value, predicate in ((rule.minimum, sh.minCount), (rule.maximum, sh.maxCount)):
        if value is not None:
            _ = actual.add((property_shape, predicate, Literal(value)))

    expected = Graph().parse(data=_render(fixture.shape or "", bindings), format="turtle")
    conforms = _conforms(data=graph, shapes=actual)
    reference_conforms = _conforms(data=graph, shapes=expected)
    return conforms == reference_conforms == fixture.expected


def _conforms(*, data: Graph, shapes: Graph) -> bool:
    from importlib import import_module  # noqa: PLC0415 -- Optional ontology extra.
    from typing import Protocol, runtime_checkable  # noqa: PLC0415 -- Optional ontology extra.

    @runtime_checkable
    class Engine(Protocol):
        def validate(  # noqa: PLR0913 -- Pin the validator safety options.
            self,
            *,
            data_graph: Graph,
            shacl_graph: Graph,
            inference: str,
            advanced: bool,
            js: bool,
            do_owl_imports: bool,
        ) -> tuple[object, object, object]: ...

    engine = import_module("pyshacl.entrypoints")
    if not isinstance(engine, Engine):
        raise TypeError("Use the supported SHACL runtime.")
    if any(str(p).rsplit("#", 1)[-1] in {"sparql", "js", "select", "ask"} for _, p, _ in shapes):
        raise ValueError("Use SHACL Core fixtures without network or script execution.")
    result, _, _ = engine.validate(
        data_graph=data,
        shacl_graph=shapes,
        inference="none",
        advanced=False,
        js=False,
        do_owl_imports=False,
    )
    if type(result) is not bool:
        raise TypeError("SHACL evaluation did not yield a validation result.")
    return result


def _seed_targets(key: PacketKey) -> set[str]:
    observable = {t.id for t in key.targets if t.disposition in ("required", "optional")}
    return {m.target for m in key.mappings if m.seeded and m.target in observable}


def _verify_review_evidence(*, review: Review, blind: Blind, key: PacketKey) -> None:
    proposals = {p.id: p for p in blind.proposals}
    targets = {target.id: target for target in key.targets}
    for grade in review.grades:
        if grade.verdict not in ("match", "extension"):
            continue
        proposal = proposals[grade.proposal]
        if not proposal.evidence:
            raise ValueError("Credit requires at least one reopenable source witness.")
        if grade.target is not None and targets[grade.target].kind != proposal.kind:
            raise ValueError("Match the kind of the observable schema meaning.")


def _mapping_counts(*, outcome: Outcome, key: PacketKey, review: Review) -> Counter[str]:
    result: Counter[str] = Counter()
    required = {target.id for target in key.targets if target.disposition == "required"}
    credited_proposals = {g.proposal: g for g in review.grades}

    exposed = {item.id: item for item in outcome.blind.mappings}
    mappings = {item.suggestion: item for item in review.mappings}
    if len(mappings) != len(review.mappings) or set(exposed) != set(mappings):
        raise ValueError("Grade every issued mapping exactly once.")
    allowed = {(m.target, m.iri, m.relation) for m in key.mappings}
    credited = set[str]()
    for ident, grade in mappings.items():
        row = exposed[ident]
        if row.relation is not None and row.relation != grade.relation:
            raise ValueError("Judge the suggested relation as issued.")
        relation = grade.relation or "unspecified"
        result[f"mappings_{relation}"] += 1
        if grade.correct:
            if (
                (grade.target, row.iri, grade.relation) not in allowed
                or not row.evidence
                or row.proposal not in credited_proposals
                or credited_proposals[row.proposal].verdict not in ("match", "extension")
                or (
                    credited_proposals[row.proposal].target is not None
                    and credited_proposals[row.proposal].target != grade.target
                )
            ):
                raise ValueError(
                    "A valid mapping requires an allowed relation and source evidence."
                )
            if grade.target is not None:
                credited.add(grade.target)
            result[f"correct_mappings_{relation}"] += 1
        elif grade.relation == "equivalent":
            result["false_equivalence"] += 1
    if outcome.arm in ("late", "guided"):
        result["seeded_required"] = len(_seed_targets(key))
        result["seeded_found"] = len(credited & _seed_targets(key))
        holdouts = {m.target for m in key.mappings if not m.seeded and m.target in required}
        result["held_out_required"] = len(holdouts)
        result["held_out_found"] = len(
            holdouts
            & {
                g.target
                for g in review.grades
                if g.verdict == "match"
                and not g.unsupported_bound
                and not g.lost_critical_condition
            }
        )
    result["correct_mappings"] = sum(grade.correct for grade in mappings.values())
    result["mappings"] = len(mappings)
    return result


def _clarification_counts(*, blind: Blind, review: Review, expected: set[str]) -> Counter[str]:
    grades = {grade.index: grade for grade in review.clarifications}
    if len(grades) != len(review.clarifications) or set(grades) != set(
        range(1, len(blind.clarifications) + 1)
    ):
        raise ValueError("Every emitted clarification needs exactly one judgment.")
    claimed: set[str] = set()
    counts: Counter[str] = Counter(
        emitted_clarifications=len(grades), expected_clarifications=len(expected)
    )
    for grade in grades.values():
        if grade.verdict == "match":
            if grade.target is None or grade.target not in expected or grade.target in claimed:
                raise ValueError("Credit each expected clarification at most once.")
            claimed.add(grade.target)
        elif grade.target is not None or (
            grade.verdict == "extension" and not grade.reason.strip()
        ):
            raise ValueError("Use targets for matches and explain justified extra clarifications.")
        counts[f"clarification_{grade.verdict}"] += 1
    return counts


def _measure_outcome(
    *,
    outcome: Outcome,
    key: PacketKey,
    judgment: Judgment,
    local_judgment: Judgment | None = None,
) -> Counter[str]:
    proposed = {p.id for p in outcome.blind.proposals}
    required = {target.id for target in key.targets if target.disposition == "required"}
    optional = frozenset(t.id for t in key.targets if t.disposition == "optional")
    expected_clarifications = {t.id for t in key.targets if t.disposition == "clarification"}
    result = Counter({"complete": int(outcome.complete)})
    # Check the two input reviews as well as the resolved review.
    local = local_judgment or judgment
    for row in (local.first, local.second):
        _ = tally(review=row, proposals=proposed, required=required, optional=optional)
        _ = _clarification_counts(blind=outcome.blind, review=row, expected=expected_clarifications)
    first_grades = {g.proposal: (g.verdict, g.target) for g in local.first.grades}
    second_grades = {g.proposal: (g.verdict, g.target) for g in local.second.grades}
    result["agreement_total"] = len(proposed)
    result["agreement"] = sum(first_grades[p] == second_grades[p] for p in proposed)
    review = select_review(judgment=local)
    if local_judgment is not None:
        mapping_review = select_review(judgment=judgment)
        if mapping_review.grades or mapping_review.checks or mapping_review.clarifications:
            raise ValueError("The late view reviews mapping suggestions on the shared local draft.")
        review = review.model_copy(update={"mappings": mapping_review.mappings})
    result.update(tally(review=review, proposals=proposed, required=required, optional=optional))
    _verify_review_evidence(review=review, blind=outcome.blind, key=key)
    result.update(_mapping_counts(outcome=outcome, key=key, review=review))
    result.update(
        _clarification_counts(blind=outcome.blind, review=review, expected=expected_clarifications)
    )
    result["review_corrections"] = len(review.corrections)
    checks = {x.fixture: x for x in review.checks}
    if len(checks) != len(review.checks) or not checks.keys() <= {f.id for f in key.fixtures}:
        raise ValueError("Bind each known executable fixture at most once.")
    checked: dict[tuple[str, bool], bool] = {}
    for f in key.fixtures:
        family = (f.alternative_group or f.id, f.alternative_group is not None)
        passed = f.id in checks and fixture_passes(
            fixture=f, binding=checks[f.id], review=review, blind=outcome.blind
        )
        checked[family] = checked.get(family, False) or passed
    result["checks"] = len(checked)
    result["checks_passed"] = sum(checked.values())
    critical = {
        (f.alternative_group or f.id, f.alternative_group is not None)
        for f in key.fixtures
        if f.critical
    }
    result["critical_failed"] = sum(not checked[family] for family in critical)
    return result


def metrics(*, counts: Counter[str]) -> dict[str, float]:
    """Compute bounded micro precision, recall, and F1 from explicit counts."""
    precision = counts["correct"] / counts["proposals"] if counts["proposals"] else 0.0
    recall = counts["recovered"] / counts["required"] if counts["required"] else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def _decision_metrics(*, counts: Counter[str]) -> dict[str, object]:
    emitted, expected, matched, extensions = (
        counts[name]
        for name in (
            "emitted_clarifications",
            "expected_clarifications",
            "clarification_match",
            "clarification_extension",
        )
    )
    clarity = Counter(
        correct=matched + extensions, proposals=emitted, recovered=matched, required=expected
    )
    scores = metrics(counts=clarity)
    return {
        "clarifications": {
            "emitted": emitted,
            "expected": expected,
            "matched": matched,
            "extensions": extensions,
            "missed": expected - matched,
            "unnecessary": counts["clarification_unnecessary"],
            "duplicates": counts["clarification_duplicate"],
            "precision": scores["precision"] if emitted else None,
            "recall": scores["recall"] if expected else None,
            "f1": scores["f1"] if expected else None,
        },
        "joint": metrics(counts=counts + clarity),
    }


def _paired(
    *, left: dict[str, Counter[str]], right: dict[str, Counter[str]], strata: dict[str, str]
) -> dict[str, float] | None:
    if left.keys() != right.keys() or not left:
        return None
    rng = Random(42)  # noqa: S311 -- Reproducible paired bootstrap.
    pools = [sorted(p for p in left if strata[p] == stratum) for stratum in STRATA]
    if any(len(pool) < MIN_BOOTSTRAP_GROUPS for pool in pools):
        return None

    def difference(ids: list[str]) -> float:
        totals = (sum((rows[p] for p in ids), Counter[str]()) for rows in (left, right))
        one, two = (metrics(counts=total)["f1"] for total in totals)
        return two - one

    draws = sorted(
        difference([p for pool in pools for p in rng.choices(pool, k=len(pool))])
        for _ in range(2_000)
    )
    return {"delta_f1": difference(sorted(left)), "lower95": draws[50], "upper95": draws[1949]}


def _campaign_outputs(
    *, campaign: Campaign, judgments: Judgments, packet_ids: set[str], arms: tuple[Arm, ...]
) -> tuple[dict[tuple[str, Arm], Outcome], dict[str, Judgment]]:
    cases: dict[tuple[str, Arm], Outcome] = {(o.packet, o.arm): o for o in campaign.outcomes}
    reviews = {item.blind_id: item for item in judgments.packets}
    blind_ids = {row.blind.id for row in cases.values()}
    if (
        len(cases) != len(campaign.outcomes)
        or len(blind_ids) != len(cases)
        or len(reviews) != len(judgments.packets)
        or not reviews.keys() <= blind_ids
        or any(p not in packet_ids or arm not in arms for p, arm in cases)
    ):
        raise ValueError("Use distinct, expected run outcomes and original blind review IDs.")
    for (packet, arm), outcome in cases.items():
        if outcome.local_sha256 != digest(blind=outcome.blind):
            raise ValueError("Saved proposal contents differ from their run digest.")
        if (
            arm == "late"
            and (open_outcome := cases.get((packet, "open"))) is not None
            and open_outcome.local_sha256 != outcome.local_sha256
        ):
            raise ValueError("Late mapping must use the identical frozen draft.")
    return cases, reviews


def scorecard(
    *, corpus: Corpus, keys: KeySet, campaign: Campaign, judgments: Judgments
) -> dict[str, object]:
    """Grade saved outputs and preserve missing work and independent-review status."""
    packets = {p.id: p for p in corpus.packets if p.split == campaign.split}
    keys_by_packet = {k.packet: k for k in keys.packets}
    expected_arms: tuple[Arm, ...] = ARMS
    if campaign.protocol == "external":
        expected_arms = ("external",)
    elif campaign.split == "development":
        expected_arms = (*ARMS, "default-cap")
    cases, reviews = _campaign_outputs(
        campaign=campaign, judgments=judgments, packet_ids=set(packets), arms=expected_arms
    )

    results: dict[str, dict[str, object]] = {}
    graded_by_arm: dict[str, dict[str, Counter[str]]] = {}
    readiness: dict[str, bool] = {}
    for arm in expected_arms:
        totals: Counter[str] = Counter()
        breakdown: dict[str, Counter[str]] = {}
        measured: dict[str, Counter[str]] = {}
        pending: list[str] = []
        missing: list[str] = []
        saved = [outcome for (_, mode), outcome in cases.items() if mode == arm]
        for p in packets.values():
            key = keys_by_packet[p.id]
            outcome = cases.get((p.id, arm))
            original = cases.get((p.id, "open")) if arm == "late" else None
            shared = reviews.get(original.blind.id) if original is not None else None
            if outcome is None:
                missing.append(p.id)
            elif (review := reviews.get(outcome.blind.id)) is not None and (
                arm != "late" or shared is not None
            ):
                measured[p.id] = _measure_outcome(
                    outcome=outcome, key=key, judgment=review, local_judgment=shared
                )
            else:
                pending.append(outcome.blind.id)
            counts = measured.get(
                p.id,
                Counter(
                    required=sum(t.disposition == "required" for t in key.targets),
                    expected_clarifications=sum(
                        t.disposition == "clarification" for t in key.targets
                    ),
                ),
            )
            totals.update(counts)
            for group in (
                f"stratum/{p.stratum}",
                *(f"format/{x}" for x in sorted({s.format for s in p.sources})),
            ):
                breakdown.setdefault(group, Counter()).update(counts)
        quality = metrics(counts=totals)
        graded_by_arm[arm] = measured
        seeded = (
            totals["seeded_found"] / totals["seeded_required"] if totals["seeded_required"] else 0.0
        )
        ready = not pending and not missing and totals["complete"] == len(packets)
        readiness[arm] = (
            ready
            and (
                arm == "late"
                or (quality["precision"] >= MIN_PRECISION and quality["recall"] >= MIN_RECALL)
            )
            and not any(
                totals[k]
                for k in (
                    "unsupported_bounds",
                    "lost_conditions",
                    "false_equivalence",
                    "critical_failed",
                )
            )
            and (arm not in ("late", "guided") or seeded >= MIN_SEEDED_COVERAGE)
        )
        results[arm] = {
            "counts": dict(totals),
            **quality,
            **_decision_metrics(counts=totals),
            "by_stratum_and_format": {
                k: {**v, **metrics(counts=v), **_decision_metrics(counts=v)}
                for k, v in breakdown.items()
            },
            "packet_macro": {
                k: mean(metrics(counts=x)[k] for x in measured.values()) for k in quality
            }
            if measured
            else {},
            "seeded_coverage": seeded,
            "pending_blind_reviews": pending,
            "missing_packets": missing,
            "incomplete_packets": [x.packet for x in saved if not x.complete],
            "status_counts": dict(Counter(x.status for x in saved)),
            "failure_counts": dict(Counter(failure for x in saved for failure in x.failures)),
            "gates_passed": readiness[arm],
        }
        if arm != "external":
            results[arm] |= _operational_metrics(outcomes=saved)
    acceptance_arms = (
        ("external",) if campaign.protocol == "external" else ("open", "late", "guided")
    )
    return {
        "split": campaign.split,
        "protocol": campaign.protocol,
        "acceptance": (
            "development"
            if campaign.split == "development"
            else "pending"
            if any(
                (outcome := cases.get((packet, arm))) is None or outcome.blind.id not in reviews
                for packet in packets
                for arm in expected_arms
            )
            else "pass"
            if all(readiness[arm] for arm in acceptance_arms)
            else "fail"
        ),
        "arms": results,
        "paired_open_vs_direct": _paired(
            left=graded_by_arm.get("open", {}),
            right=graded_by_arm.get("direct", {}),
            strata={p.id: p.stratum for p in packets.values()},
        ),
        "paired_open_vs_guided": _paired(
            left=graded_by_arm.get("open", {}),
            right=graded_by_arm.get("guided", {}),
            strata={p.id: p.stratum for p in packets.values()},
        ),
    }


def _operational_metrics(*, outcomes: list[Outcome]) -> dict[str, float | int]:
    return {
        "latency_seconds": sum(x.latency_seconds for x in outcomes),
        "provider_seconds": sum(x.provider_seconds for x in outcomes),
        "input_tokens": sum(x.input_tokens for x in outcomes),
        "output_tokens": sum(x.output_tokens for x in outcomes),
        "retries": sum(x.retries for x in outcomes),
        "cost_usd": sum(x.cost_usd for x in outcomes if x.cost_usd is not None),
        "unpriced_outcomes": sum(x.cost_usd is None for x in outcomes),
    }
