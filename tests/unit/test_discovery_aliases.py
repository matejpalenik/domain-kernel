"""Test alias candidates at the standalone discovery boundary."""

from domain_kernel.discovery.application.claim_extraction import Anchor, Claim
from domain_kernel.discovery.infrastructure.langgraph_gateway import (
    _alias_groups,  # pyright: ignore[reportPrivateUsage] -- candidate grouping precedes inference
)


def test_reconcile_offers_distinct_names_from_one_exact_evidence_anchor() -> None:
    quote = "The maître and the steward are two names for the same post. A gate is nearby."

    def concept(*, name: str, citation: int) -> Claim:
        return Claim(
            kind="concept",
            name=name,
            title=name,
            meaning=quote,
            source=None,
            target=None,
            conditions=[],
            exceptions=[],
            evidence=[Anchor(citation=citation, quote=quote)],
        )

    rows = {
        name: concept(name=name, citation=n)
        for name, n in (("maitre", 1), ("steward", 1), ("stew", 1), ("gate", 1), ("nearby", 2))
    }
    groups = [[value.name for value in batch] for batch in _alias_groups(rows)]
    assert groups == [["maitre", "steward"], ["gate", "maitre", "steward"]]
