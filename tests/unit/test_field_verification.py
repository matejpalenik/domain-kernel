from __future__ import annotations

from copy import deepcopy

import pytest

from domain_kernel.discovery.application.claim_extraction import (
    Anchor,
    FieldDecision,
    IdentifiedClaim,
    Qualification,
    Verdict,
)
from domain_kernel.discovery.application.field_verification import assess

_QUOTE = "A report may be distributed unless it bears a hold."
_SOURCE = Anchor(citation=1, quote=_QUOTE)


def _claim() -> IdentifiedClaim:
    return IdentifiedClaim(
        claim_id="c-reviewed",
        kind="relationship",
        name="distribution",
        title="Distribution",
        meaning="A report may be distributed.",
        source="author",
        target="report",
        conditions=[],
        exceptions=[Qualification(text="Unless on hold.", evidence=[_SOURCE])],
        evidence=[_SOURCE],
    )


def _vote() -> Verdict:
    present = FieldDecision(status="supported", evidence=_SOURCE)
    absent = FieldDecision(status="not_applicable", evidence=None)
    return Verdict(
        claim_id="c-reviewed",
        meaning=present,
        actor=present,
        object=present,
        recipient=absent,
        modality=present,
        conditions=absent,
        exceptions=present,
        reason="The document identifies the restriction.",
    )


def _resolve(anchor: Anchor) -> Anchor | None:
    return Anchor(citation=47, quote=anchor.quote) if anchor == _SOURCE else None


@pytest.mark.parametrize("field", ["actor", "object", "modality", "exceptions"])
def test_any_disputed_field_prevents_approval(field: str) -> None:
    vote = _vote().model_copy(
        update={field: FieldDecision(status="contradicted", evidence=_SOURCE)}
    )
    result = assess(claim=_claim(), votes=[vote], stage="verify", resolve=_resolve)
    assert result.status == "contradicted"
    assert field in result.detail
    assert result.verdict is not None
    assert result.verdict.meaning.evidence == Anchor(citation=47, quote=_QUOTE)
    assert vote.meaning.evidence == _SOURCE


def test_duplicate_missing_and_unrelated_ids_never_substitute_for_a_verdict() -> None:
    claim = _claim()
    vote = _vote()
    unrelated = vote.model_copy(update={"claim_id": "another-claim"})
    for votes in ([], [unrelated], [vote, deepcopy(vote)]):
        assert (
            assess(claim=claim, votes=votes, stage="verify", resolve=_resolve).status == "invalid"
        )
    for votes in ([vote, unrelated], [unrelated, vote]):
        assert (
            assess(claim=claim, votes=votes, stage="verify", resolve=_resolve).status == "supported"
        )


def test_unsupported_exception_and_broken_anchors_cannot_pass() -> None:
    for decision in (
        FieldDecision(status="not_applicable", evidence=None),
        FieldDecision(status="supported", evidence=None),
        FieldDecision(status="supported", evidence=Anchor(citation=2, quote=_QUOTE)),
    ):
        vote = _vote().model_copy(update={"exceptions": decision})
        result = assess(claim=_claim(), votes=[vote], stage="verify", resolve=_resolve)
        assert result.status == "invalid"
        assert "exceptions" in result.detail
