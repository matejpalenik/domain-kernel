"""Versioned discovery handoff and keyed endpoint verification schemas."""

from __future__ import annotations

from typing import Literal

from domain_kernel.discovery.application.claim_extraction import (
    Anchor,
    ClosedRecord,
    LocatedMention,
)
from domain_kernel.shared.hashing import Hashing

VERSION = "evidence-bound-v2"
REPAIR_VERSION = "evidence-bound-v3"


def approved_key(*, identity: str, revision: int) -> str:
    """Name an exact approved concept snapshot independently of its lookup name."""
    return "approved-" + Hashing.hash_json(value=(identity, revision)).value.removeprefix("sha256:")


VERIFY_ENDPOINTS = (
    " Echo the exact claim_id and binding_key for every supplied edge. Return one verdict per "
    "edge. For a supported verdict, copy the exact source wording that establishes the directed "
    "action and connects the specified participants. Include separate exact excerpts where "
    "necessary to connect a participant across clauses. An identical label alone does not "
    "connect two occurrences. Use one-based citations from the supplied passages. "
    "Treat the binding keys as opaque values."
)

MINING = (
    " Cite each participant's actual occurrence in the relationship's evidence. "
    "Use a separate mention reference for each occurrence. Reuse a reference only when "
    "the relationship evidence covers that exact occurrence. Give local context when a "
    "designation recurs. For an approved concept, cite a source statement identifying "
    "the participant as that exact concept."
)


class EndpointVerdict(ClosedRecord):
    """Support for one exact directed binding."""

    claim_id: str
    binding_key: str
    status: Literal["supported", "partly_supported", "contradicted", "insufficient"]
    evidence: list[Anchor]
    reason: str


class EndpointVerdicts(ClosedRecord):
    """The endpoint batch response keyed by claim ID."""

    verdicts: list[EndpointVerdict]


class EndpointReference(ClosedRecord):
    """An occurrence and the resolved assembly identity, if known."""

    occurrence: LocatedMention
    concept_key: str | None


class EdgeBinding(ClosedRecord):
    """The stable identity handoff for one relationship occurrence."""

    claim_id: str
    proposal_name: str | None
    source: EndpointReference | None
    target: EndpointReference | None
    evidence: list[Anchor]
    identity_evidence: list[Anchor]
    origin_claim_ids: list[str]
    reason: str | None
    previous_source: EndpointReference | None = None
    previous_target: EndpointReference | None = None


class BindingEnvelope(ClosedRecord):
    """SDK-generated binding data outside the provider-facing proposal schema."""

    contract: Literal["evidence-bound-v2", "evidence-bound-v3"] = VERSION
    concepts: dict[str, str]
    edges: list[EdgeBinding]
