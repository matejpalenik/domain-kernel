"""Verified relationship occurrences retain semantics, evidence and explicit projection lineage."""

from __future__ import annotations

from domain_kernel.discovery.application.claim_extraction import (
    Alias,
    Anchor,
    IdentifiedClaim,
    Qualification,
)
from domain_kernel.discovery.application.claim_graph import assemble_claims, proposal_names


def concept(name: str, *, meaning: str | None = None) -> IdentifiedClaim:
    return IdentifiedClaim(
        claim_id=f"id-{name}",
        name=name,
        title=name,
        kind="concept",
        meaning=meaning or name,
        source=None,
        target=None,
        evidence=[Anchor(citation=1, quote=meaning or name)],
        conditions=[],
        exceptions=[],
    )


def edge(claim_id: str, *, citation: int = 1) -> IdentifiedClaim:
    quote = Anchor(citation=citation, quote="The customer sends a form when asked.")
    return IdentifiedClaim(
        claim_id=claim_id,
        name="sends",
        title="Sends",
        kind="relationship",
        meaning="The customer sends a form.",
        source="customer",
        target="form",
        evidence=[quote],
        conditions=[Qualification(text="when asked", evidence=[quote])],
        exceptions=[],
    )


def test_duplicate_assertions_merge_exact_evidence_at_each_qualification() -> None:
    first, second = edge("a"), edge("b", citation=2)
    graph = assemble_claims(
        accepted=[first, second], aliases={}, approved_concepts={"customer", "form"}
    )
    (combined,) = graph.claims
    assert graph.origins[combined.claim_id] == ["a", "b"]
    assert [a.citation for a in combined.evidence] == [1, 2]
    assert [a.citation for a in combined.conditions[0].evidence] == [1, 2]
    assert len(first.evidence) == len(first.conditions[0].evidence) == len(second.evidence) == 1
    assert proposal_names(claims=graph.claims) == {"a": "sends"}


def test_conservative_consolidation_preserves_different_conditions() -> None:
    first, second, different = edge("first"), edge("second", citation=2), edge("different")
    second.conditions[0].text = "when asked."
    different.conditions[0].text = "when explicitly required"
    graph = assemble_claims(
        accepted=[first, second, different],
        aliases={},
        approved_concepts={"customer", "form"},
        consolidate_punctuation=True,
    )
    assert graph.origins == {"first": ["first", "second"], "different": ["different"]}
    combined = next(row for row in graph.claims if row.claim_id == "first")
    assert [a.citation for a in combined.conditions[0].evidence] == [1, 2]


def test_qualified_or_reversed_edges_survive_reserved_names_and_input_reordering() -> None:
    original = edge("original")
    exception = edge("exception")
    exception.exceptions, exception.conditions = exception.conditions, []
    reversed_edge = edge("reverse")
    reversed_edge.source, reversed_edge.target = reversed_edge.target, reversed_edge.source
    claims = [original, exception, reversed_edge, concept("customer-sends-form"), concept("sends")]
    for order in (claims, list(reversed(claims))):
        graph = assemble_claims(accepted=order, aliases={}, approved_concepts={"customer", "form"})
        keys = proposal_names(claims=graph.claims)
        assert len(keys) == len(set(keys.values())) == len(claims)
        assert keys["id-sends"] == "sends"
        assert keys["id-customer-sends-form"] == "customer-sends-form"
        assert keys["reverse"] == "form-sends-customer"
        assert graph.findings == []
        assert keys == proposal_names(claims=list(reversed(graph.claims)))


def test_alias_cannot_retarget_an_edge_via_a_different_formulation() -> None:
    customer = concept("customer")
    client = concept("client")
    different = concept("client", meaning="Client software.")
    different.claim_id = "second-client"
    relationship = edge("sends")
    relationship.source = "client"
    alias = Alias(
        alternate="client",
        preferred="customer",
        alternate_quote="client",
        preferred_quote="customer",
        reason="The same participant.",
    )
    graph = assemble_claims(
        accepted=[customer, client, different, relationship],
        aliases={"client": alias},
        approved_concepts={"form"},
    )
    assert all(c.claim_id != "sends" for c in graph.claims)
    assert any(f.claim_id == "sends" and "ambiguous" in f.detail.lower() for f in graph.findings)


def test_incompatible_repairs_for_one_source_occurrence_require_review() -> None:
    first = edge("same-parent")
    second = edge("same-parent", citation=2)
    second.target = "supplier"
    graph = assemble_claims(
        accepted=[first, second], aliases={}, approved_concepts={"customer", "form", "supplier"}
    )
    assert not graph.claims
    assert {f.claim_id for f in graph.findings} == {"same-parent"}


def test_canonical_edge_carries_the_exact_evidence_for_its_endpoint_rewrite() -> None:
    client = concept("client")
    customer = concept("customer")
    customer.evidence.append(Anchor(citation=7, quote="Unrelated background."))
    link = edge("origin")
    link.source = "client"
    alias = Alias(
        alternate="client",
        preferred="customer",
        alternate_quote="client",
        preferred_quote="customer",
        reason="Same participant.",
    )
    graph = assemble_claims(
        accepted=[client, customer, link], aliases={"client": alias}, approved_concepts={"form"}
    )
    result = next(c for c in graph.claims if c.claim_id == link.claim_id)
    assert result.source == "customer"
    assert {a.quote for a in result.evidence} == {link.evidence[0].quote, "client", "customer"}
    assert len(link.evidence) == 1
