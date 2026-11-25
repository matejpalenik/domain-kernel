"""Verify the procurement evaluation's evidence and accounting boundaries."""

from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from benchmarks.procurement import MeteredLuna
from benchmarks.procurement_data import (
    Corpus,
    Fixture,
    KeySet,
    Packet,
    PacketKey,
    Slot,
    Source,
    Target,
    choose_packets,
    validate_capture,
    visible_html,
)
from benchmarks.procurement_run import ATTEMPTS, PROFILE
from benchmarks.procurement_score import (
    Anchor,
    Blind,
    Campaign,
    CheckBinding,
    ClarificationGrade,
    Grade,
    Judgment,
    Judgments,
    Outcome,
    Proposal,
    ProposedRule,
    Review,
    Submission,
    SubmittedPacket,
    digest,
    fixture_passes,
    scorecard,
    select_review,
    submission_campaign,
    tally,
)
from domain_kernel import LangGraphDiscoveryGateway, LiteLLMGateway


def test_visible_html_keeps_tables_and_drops_embedded_answers() -> None:
    fixture = (
        b'<table data-gold="secret"><tr><th colspan="2">Lot</th><td>Steel</td></tr></table>'
        b'<script type="application/ld+json">{"reference": "secret"}</script>'
        b"<p hidden>secret</p><p>Published &amp; signed</p>"
    )
    output = visible_html(content=fixture)
    assert b"secret" not in output
    assert b'<th colspan="2">Lot</th>' in output
    assert b"Published &amp; signed" in output


def test_pick_never_splits_groups_and_preserves_six_eighteen() -> None:
    groups = {
        stratum: [(f"{stratum}-{i}", f"{stratum}-group-{i}") for i in range(10)]
        for stratum in ("single", "linked", "buyer")
    }
    first = choose_packets(groups=groups, required_development="single-0")
    assert first == choose_packets(groups=groups, required_development="single-0")
    assert Counter(first.values()) == {"development": 6, "locked": 18}
    assert first["single-0"] == "development"


def test_grade_keeps_valid_extensions_and_counts_unrecovered_targets() -> None:
    review = Review(
        reviewer="reviewer-a",
        grades=(
            Grade(proposal="p1", verdict="match", target="required-1"),
            Grade(proposal="p2", verdict="extension"),
            Grade(proposal="p3", verdict="duplicate"),
        ),
    )
    required = {"required-1", "required-2"}
    proposals = {"p1", "p2", "p3"}
    measured = tally(review=review, proposals=proposals, required=required)
    assert measured["correct"] == measured["required"] == len(required)
    assert measured["recovered"] == 1
    assert measured["proposals"] == len(proposals)


def test_grade_rejects_multi_credit() -> None:
    with pytest.raises(ValueError, match="one-to-one"):
        _ = tally(
            review=Review(
                reviewer="reviewer-a",
                grades=(
                    Grade(proposal="p1", verdict="match", target="required-1"),
                    Grade(proposal="p2", verdict="match", target="required-1"),
                ),
            ),
            proposals={"p1", "p2"},
            required={"required-1"},
        )


def test_keyed_optional_extension_earns_precision_credit_only() -> None:
    counts = tally(
        review=Review(
            reviewer="reviewer-a",
            grades=(Grade(proposal="extra", verdict="extension", target="optional-meaning"),),
        ),
        proposals={"extra"},
        required={"required-meaning"},
        optional=frozenset({"optional-meaning"}),
    )
    assert counts["correct"] == 1
    assert counts["recovered"] == 0


def test_offline_cli_has_no_network_requirement(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        validate_capture(path=tmp_path / "unavailable.pdf", expected="0" * 64)


def test_metering_preserves_v23_capability_and_sdk_retry_budget(tmp_path: Path) -> None:
    metered = MeteredLuna(provider=LiteLLMGateway(api_key="unused-in-offline-test"))
    staged = LangGraphDiscoveryGateway(
        gateway=metered, directory=tmp_path, profile=PROFILE, stage_max_attempts=ATTEMPTS
    )
    assert staged.discovery_stage_attempts == ATTEMPTS


def test_functional_check_rejects_reversed_endpoint_roles() -> None:
    fixture = Fixture(
        id="separate-procurement-lots",
        question="cq",
        modelet="procurement-lot",
        slots=(
            Slot(name="process", kind="concept", target="procedure"),
            Slot(name="division", kind="concept", target="lot"),
            Slot(
                name="divides",
                kind="relationship",
                target="has_lot",
                endpoints=("process", "division"),
            ),
        ),
        graph="<urn:case:procedure> {{divides}} <urn:case:lot1> .",
        query="SELECT ?x WHERE { <urn:case:procedure> {{divides}} ?x . }",
        expected=(("urn:case:lot1",),),
    )
    procedure = Proposal(id="proc", title="Procedure", meaning="Procurement", kind="concept")
    lot = Proposal(id="lot", title="Lot", meaning="Subdivided scope", kind="concept")
    relation = Proposal(
        id="edge",
        title="Contains",
        meaning="A procedure contains a lot.",
        kind="relationship",
        source="proc",
        target="lot",
    )
    draft = Blind(id="blind-a", proposals=(procedure, lot, relation))
    binding = CheckBinding(
        fixture=fixture.id, slots={"process": "proc", "division": "lot", "divides": "edge"}
    )
    review = Review(
        reviewer="ontology-a",
        grades=(
            Grade(proposal="proc", verdict="match", target="procedure"),
            Grade(proposal="lot", verdict="match", target="lot"),
            Grade(proposal="edge", verdict="match", target="has_lot"),
        ),
    )
    assert fixture_passes(fixture=fixture, binding=binding, review=review, blind=draft)
    reversed_relation = relation.model_copy(update={"source": "lot", "target": "proc"})
    reversed_draft = draft.model_copy(update={"proposals": (procedure, lot, reversed_relation)})
    assert not fixture_passes(fixture=fixture, binding=binding, review=review, blind=reversed_draft)


def test_late_review_reuses_identical_local_content() -> None:
    draft = Blind(id="blind-a", clarifications=("Which policy applies?",))
    assert digest(blind=draft) == digest(blind=draft.model_copy(update={"id": "blind-b"}))


def test_independent_disagreement_requires_adjudication() -> None:
    first = Review(reviewer="a", grades=(Grade(proposal="p", verdict="extension"),))
    second = Review(reviewer="b", grades=(Grade(proposal="p", verdict="unsupported"),))
    judgment = Judgment(blind_id="blind-a", first=first, second=second)
    with pytest.raises(ValueError, match="third-party adjudication"):
        _ = select_review(judgment=judgment)
    resolution = first.model_copy(update={"reviewer": "c"})
    assert select_review(judgment=judgment.model_copy(update={"adjudication": resolution})) == (
        resolution
    )


def _award_packet() -> Packet:
    return Packet(
        id="award",
        procedure="p",
        buyer="Buyer",
        group="independent",
        stratum="single",
        split="development",
        published=date(2025, 7, 9),
        purpose="Model closure decisions",
        questions=(),
        sources=(
            Source(
                id="notice",
                file="notice.pdf",
                sha256="a" * 64,
                url="https://example.org/notice.pdf",
                publisher="Buyer",
                format="pdf",
                reuse="Test fixture",
            ),
        ),
    )


def _clarification_score(
    *, blind: Blind, review: Review, expected: tuple[str, ...]
) -> dict[str, object]:
    packet = _award_packet()
    key = PacketKey(
        packet=packet.id,
        targets=tuple(
            Target(
                id=target,
                question="closure",
                kind="rule",
                meaning="Determine which decision occurred",
                disposition="clarification",
            )
            for target in expected
        ),
    )
    outcome = Outcome(
        packet=packet.id,
        arm="direct",
        complete=True,
        status="complete",
        blind=blind,
        local_sha256=digest(blind=blind),
        latency_seconds=1.0,
    )
    report = scorecard(
        corpus=Corpus(packets=(packet,)),
        keys=KeySet(corpus_sha256="public", packets=(key,)),
        campaign=Campaign(
            corpus_sha256="public", keys_sha256="key", split="development", outcomes=(outcome,)
        ),
        judgments=Judgments(
            packets=(
                Judgment(
                    blind_id=blind.id,
                    first=review,
                    second=review.model_copy(update={"reviewer": "other"}),
                ),
            )
        ),
    )
    arms = TypeAdapter(dict[str, dict[str, object]]).validate_python(report["arms"])
    return arms["direct"]


def test_clarification_score_penalizes_unnecessary_and_duplicate_questions() -> None:
    blind = Blind(
        id="case",
        clarifications=(
            "Was the lot closed after withdrawals or a finding of inadmissibility?",
            "Who is the buyer?",
            "Was it withdrawals or inadmissibility?",
        ),
    )
    review = Review(
        reviewer="a",
        grades=(),
        clarifications=(
            ClarificationGrade(index=1, verdict="match", target="closure"),
            ClarificationGrade(index=2, verdict="unnecessary"),
            ClarificationGrade(index=3, verdict="duplicate"),
        ),
    )
    score = _clarification_score(blind=blind, review=review, expected=("closure", "authority"))
    assert score["precision"] == 0.0
    assert score["clarifications"] == {
        "emitted": 3,
        "matched": 1,
        "extensions": 0,
        "unnecessary": 1,
        "duplicates": 1,
        "expected": 2,
        "missed": 1,
        "precision": 1 / 3,
        "recall": 0.5,
        "f1": 0.4,
    }
    assert score["joint"] == {"precision": 1 / 3, "recall": 0.5, "f1": 0.4}


def test_missing_clarification_judgment_cannot_hide_an_extra_question() -> None:
    blind = Blind(id="case", clarifications=("Who is the buyer?",))
    review = Review(reviewer="a", grades=())
    with pytest.raises(ValueError, match="Every emitted clarification"):
        _ = _clarification_score(blind=blind, review=review, expected=())


def test_external_graph_without_review_can_be_scored_on_the_same_key() -> None:
    packet = _award_packet()
    corpus = Corpus(packets=(packet,))
    key = PacketKey(
        packet=packet.id,
        targets=(
            Target(
                id="lot-result",
                question="closure",
                kind="concept",
                meaning="The reported outcome of a lot",
                disposition="required",
            ),
            Target(
                id="closure",
                question="closure",
                kind="rule",
                meaning="The reason requires a buyer record",
                disposition="clarification",
            ),
        ),
    )
    legitimate = Proposal(
        id="a1",
        title="Lot result",
        meaning="The reported outcome of a lot",
        kind="concept",
        evidence=(
            Anchor(
                source="notice",
                revision=f"sha256:{packet.sources[0].sha256}",
                locator="page 1",
                quote="The evening service lot closed without award.",
            ),
        ),
    )
    unsupported = Proposal(id="a2", title="Guarantor", meaning="A guarantor", kind="concept")
    submission = Submission(
        corpus_sha256="public",
        split="development",
        packets=(SubmittedPacket(packet=packet.id, proposals=(legitimate, unsupported)),),
    )
    campaign = submission_campaign(submission=submission, corpus=corpus, keys_sha256="key")
    assert len(campaign.outcomes) == 1
    view = campaign.outcomes[0].blind
    assert view.proposals == (legitimate, unsupported)
    review = Review(
        reviewer="a",
        grades=(
            Grade(proposal="a1", verdict="match", target="lot-result"),
            Grade(proposal="a2", verdict="unsupported"),
        ),
    )
    report = scorecard(
        corpus=corpus,
        keys=KeySet(corpus_sha256="public", packets=(key,)),
        campaign=campaign,
        judgments=Judgments(
            packets=(
                Judgment(
                    blind_id=view.id,
                    first=review,
                    second=review.model_copy(update={"reviewer": "b"}),
                ),
            )
        ),
    )
    arms = TypeAdapter(dict[str, dict[str, object]]).validate_python(report["arms"])
    assert set(arms) == {"external"}
    score = arms["external"]
    half_credit = 0.5
    assert score["missing_packets"] == []
    assert score["precision"] == half_credit
    assert score["recall"] == 1.0
    assert score["joint"] == {"precision": half_credit, "recall": half_credit, "f1": half_credit}
    clarifications = TypeAdapter(dict[str, object]).validate_python(score["clarifications"])
    assert clarifications["missed"] == 1


@pytest.mark.parametrize(("bound", "passes"), [(1, True), (0, False)])
def test_data_fixture_checks_the_bound_in_the_proposed_rule(*, bound: int, passes: bool) -> None:
    fixture = Fixture(
        id="specified-contract",
        question="cq",
        modelet="conditional-award",
        slots=(
            Slot(name="case", kind="concept", target="procedure"),
            Slot(name="contract", kind="concept", target="contract"),
            Slot(name="issued", kind="concept", target="signed"),
            Slot(
                name="has", kind="relationship", target="connects", endpoints=("case", "contract")
            ),
            Slot(name="rule", kind="rule", target="rule"),
        ),
        graph="<urn:case:signed-without-contract> a {{issued}} .",
        expected=False,
        shape=(
            "@prefix sh: <http://www.w3.org/ns/shacl#> . "
            "{{rule}} a sh:NodeShape ; sh:targetClass {{issued}} ; "
            "sh:property [ sh:path {{has}} ; sh:class {{contract}} ; sh:minCount 1 ] ."
        ),
    )
    rows = tuple(
        Proposal(id=ident, title=ident, meaning=ident, kind="concept")
        for ident in ("procedure", "contract", "signed")
    )
    edge = Proposal(
        id="connects",
        title="Records contract",
        meaning="A procedure records a signed contract.",
        kind="relationship",
        source="procedure",
        target="contract",
    )
    rule = Proposal(
        id="rule",
        title="Signed procedure records a contract",
        meaning="A signed procedure records at least one contract.",
        kind="rule",
        rule=ProposedRule(
            focus="procedure", relationship="connects", minimum=bound, applicable_class="signed"
        ),
    )
    proposed = (*rows, edge, rule)
    assert (
        fixture_passes(
            fixture=fixture,
            binding=CheckBinding(
                fixture=fixture.id, slots={s.name: s.target for s in fixture.slots}
            ),
            review=Review(
                reviewer="ontology-a",
                grades=tuple(Grade(proposal=p.id, verdict="match", target=p.id) for p in proposed),
            ),
            blind=Blind(id="blind", proposals=proposed),
        )
        == passes
    )
