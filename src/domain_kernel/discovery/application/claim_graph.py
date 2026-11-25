"""Project verified source assertions into proposed definitions with traceable identities."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain_kernel.discovery.application import evidence_binding
from domain_kernel.discovery.application.claim_extraction import (
    BoundClaim,
    Finding,
    VerifiedAlias,
    normalized,
)
from domain_kernel.shared.hashing import hash_json

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from domain_kernel.discovery.application.claim_extraction import (
        Alias,
        BatchResult,
        Claim,
        IdentifiedClaim,
        Verdict,
    )


type _LegacyAssertion = tuple[
    str, str, str | None, str | None, str, tuple[str, ...], tuple[str, ...]
]
type _Assertion = (
    _LegacyAssertion | tuple[*_LegacyAssertion, str | None, tuple[tuple[str, ...], ...] | None]
)

AMBIGUOUS_ENDPOINT = "The endpoint name is ambiguous across source formulations."


def _assertion(claim: Claim, *, consolidate_punctuation: bool = False) -> _Assertion:
    # Evidence identifies an occurrence. Equal assertions can accumulate independent support.
    def prose(text: str) -> str:
        value = normalized(text)
        return value.removesuffix(".") if consolidate_punctuation else value

    core = (
        claim.kind,
        claim.name,
        claim.source,
        claim.target,
        prose(claim.meaning),
        tuple(prose(q.text) for q in claim.conditions),
        tuple(prose(q.text) for q in claim.exceptions),
    )
    if isinstance(claim, BoundClaim):
        return (*core, claim.modality, evidence_binding.qualifier_paths(claim.qualifiers))
    return core


def _combine_support(*, into: IdentifiedClaim, other: IdentifiedClaim) -> None:
    for first, second in zip(
        (into, *into.conditions, *into.exceptions),
        (other, *other.conditions, *other.exceptions),
        strict=True,
    ):
        for anchor in second.evidence:
            if anchor not in first.evidence:
                first.evidence.append(anchor)


@dataclass(kw_only=True)
class ClaimGraph:
    """Inspectable assembly including every accepted occurrence's fate."""

    claims: list[IdentifiedClaim] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    origins: dict[str, list[str]] = field(default_factory=dict)

    def represent(self, *, claim: IdentifiedClaim, original_id: str) -> None:
        """Associate an earlier occurrence with the claim representing it."""
        ids = self.origins.setdefault(claim.claim_id, [])
        if original_id not in ids:
            ids.append(original_id)

    def hold(self, *, claim: IdentifiedClaim, reason: str) -> None:
        """Record why an accepted occurrence requires further review."""
        self.findings.append(
            Finding(stage="reconcile", claim_id=claim.claim_id, name=claim.name, detail=reason)
        )


def ambiguous_concept_names(*, occurrences: Iterable[IdentifiedClaim]) -> set[str]:
    """A source lookup name can identify several incompatible or unreviewed formulations."""
    by_name: dict[str, set[_Assertion]] = defaultdict(set)
    for claim in occurrences:
        if claim.kind == "concept":
            by_name[claim.name].add(_assertion(claim))
    return {name for name, assertions in by_name.items() if len(assertions) > 1}


def _merge_concepts(
    *, graph: ClaimGraph, occurrences: Sequence[IdentifiedClaim], ambiguous: set[str]
) -> dict[str, IdentifiedClaim]:
    merged: dict[_Assertion, IdentifiedClaim] = {}
    for c in occurrences:
        if c.kind != "concept":
            continue
        key = _assertion(c)
        if key not in merged:
            merged[key] = c.model_copy(deep=True)
            graph.claims.append(merged[key])
        concept = merged[key]
        _combine_support(into=concept, other=c)
        graph.represent(claim=concept, original_id=c.claim_id)
        if c.name in ambiguous:
            graph.findings.append(
                Finding(
                    stage="reconcile",
                    claim_id=c.claim_id,
                    name=c.name,
                    detail="Review the distinct concept formulations sharing this name.",
                )
            )
    return {c.name: c for c in merged.values() if c.name not in ambiguous}


def _merge_aliases(
    *, graph: ClaimGraph, aliases: Mapping[str, Alias], unique: Mapping[str, IdentifiedClaim]
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for alias in aliases.values():
        old, new = unique.get(alias.alternate), unique.get(alias.preferred)
        if (
            old is None
            or new is None
            or [q.text for q in old.conditions] != [q.text for q in new.conditions]
            or [q.text for q in old.exceptions] != [q.text for q in new.exceptions]
            or all(a.quote != alias.alternate_quote for a in old.evidence)
            or all(a.quote != alias.preferred_quote for a in new.evidence)
        ):
            continue
        _combine_support(into=new, other=old)
        for origin in graph.origins.pop(old.claim_id):
            graph.represent(claim=new, original_id=origin)
        resolved[old.name] = new.name
    graph.claims = [c for c in graph.claims if c.name not in resolved]
    return resolved


def _consistent_occurrences(
    *, accepted: Iterable[IdentifiedClaim], graph: ClaimGraph
) -> list[IdentifiedClaim]:
    by_origin: dict[str, set[_Assertion]] = defaultdict(set)
    rows = list(accepted)
    for c in rows:
        by_origin[c.claim_id].add(_assertion(c))
    retained: list[IdentifiedClaim] = []
    for c in rows:
        if len(by_origin[c.claim_id]) == 1:
            retained.append(c)
        else:
            graph.hold(
                claim=c, reason="Conflicting repairs for one occurrence. Review both formulations."
            )
    return retained


def _link_alias_evidence(
    *,
    claim: IdentifiedClaim,
    resolved: Mapping[str, str],
    aliases: Mapping[str, Alias],
    concepts: Mapping[str, IdentifiedClaim],
) -> None:
    for name in (claim.source, claim.target):
        if name is None or name not in resolved:
            continue
        alias = aliases[name]
        if isinstance(alias, VerifiedAlias) and alias.identity_witness not in claim.evidence:
            claim.evidence.append(alias.identity_witness)
        for key, quote in ((name, alias.alternate_quote), (resolved[name], alias.preferred_quote)):
            for anchor in concepts[key].evidence:
                if anchor.quote == quote and anchor not in claim.evidence:
                    claim.evidence.append(anchor)


def assemble_claims(
    *,
    accepted: Iterable[IdentifiedClaim],
    aliases: Mapping[str, Alias],
    approved_concepts: set[str],
    consolidate_punctuation: bool = False,
) -> ClaimGraph:
    """Resolve endpoints before grouping, keeping direction, wording and qualifiers in identity."""
    graph = ClaimGraph()
    occurrences = _consistent_occurrences(accepted=accepted, graph=graph)
    ambiguous = ambiguous_concept_names(occurrences=occurrences)
    concepts = _merge_concepts(graph=graph, occurrences=occurrences, ambiguous=ambiguous)
    resolved = _merge_aliases(graph=graph, aliases=aliases, unique=concepts)
    names = approved_concepts | (concepts.keys() - resolved.keys())
    edges: dict[_Assertion, IdentifiedClaim] = {}
    for original in occurrences:
        if original.kind != "relationship":
            continue
        if original.source in ambiguous or original.target in ambiguous:
            graph.hold(claim=original, reason=AMBIGUOUS_ENDPOINT)
            continue
        c = original.model_copy(deep=True)
        _link_alias_evidence(claim=c, resolved=resolved, aliases=aliases, concepts=concepts)
        if c.source is not None:
            c.source = resolved.get(c.source, c.source)
        if c.target is not None:
            c.target = resolved.get(c.target, c.target)
        if c.source not in names or c.target not in names:
            graph.hold(claim=c, reason="Unresolved endpoint; keep for review.")
            continue
        key = _assertion(c, consolidate_punctuation=consolidate_punctuation)
        edge = edges.get(key)
        if edge is None:
            edges[key] = edge = c
            graph.claims.append(edge)
        else:
            _combine_support(into=edge, other=c)
        graph.represent(claim=edge, original_id=c.claim_id)
    return graph


def _include_verdict_support(*, claim: IdentifiedClaim, verdict: Verdict) -> None:
    for dimension in (
        verdict.meaning,
        verdict.actor,
        verdict.object,
        verdict.recipient,
        verdict.modality,
    ):
        if (
            dimension.status == "supported"
            and dimension.evidence is not None
            and dimension.evidence not in claim.evidence
        ):
            claim.evidence.append(dimension.evidence)
    for qualifiers, decision in (
        (claim.conditions, verdict.conditions),
        (claim.exceptions, verdict.exceptions),
    ):
        if decision.status == "supported" and decision.evidence is not None:
            # One field verdict covers the set. Assign it to a specific qualifier only when
            # there is one; the original evidence remains attached to every qualification.
            target = qualifiers[0].evidence if len(qualifiers) == 1 else claim.evidence
            if decision.evidence not in target:
                target.append(decision.evidence)


def include_verified_evidence(*, graph: ClaimGraph, batches: Sequence[BatchResult]) -> None:
    """Carry resolved field evidence into the proposed definition after all verification."""
    accepted = {(c.claim_id, c.meaning) for b in batches for c in b.accepted}
    decisions: dict[str, list[Verdict]] = defaultdict(list)
    for b in batches:
        for a in b.assessments:
            if (
                a.status == "supported"
                and (a.claim_id, a.meaning) in accepted
                and a.verdict is not None
            ):
                decisions[a.claim_id].append(a.verdict)
    for c in graph.claims:
        for origin in graph.origins[c.claim_id]:
            for verdict in decisions[origin]:
                _include_verdict_support(claim=c, verdict=verdict)


def proposal_names(*, claims: Sequence[IdentifiedClaim]) -> dict[str, str]:
    """Give colliding predicate occurrences directed keys ahead of model-name reservation.

    The source predicate and each contributing claim ID stay in the audit. Only proposals
    sharing a name require disambiguation. Authored definitions keep normal reservation rules.
    """
    counts = Counter(c.name for c in claims)
    result: dict[str, str] = {}
    directed: dict[str, list[IdentifiedClaim]] = defaultdict(list)
    scoped: list[tuple[str, IdentifiedClaim]] = []
    ambiguous = ambiguous_concept_names(occurrences=claims)
    for c in claims:
        if c.kind == "concept" and c.name in ambiguous:
            scoped.append((c.name, c))
        elif c.kind == "concept" or counts[c.name] == 1:
            result[c.claim_id] = c.name
        else:
            directed[f"{c.source}-{c.name}-{c.target}"].append(c)
    reserved = set(result.values())
    # Allocate the unambiguous directed keys first so a generated scoped name cannot take one.
    for base, group in directed.items():
        if len(group) == 1 and base not in reserved:
            result[group[0].claim_id] = base
            reserved.add(base)
        else:
            scoped.extend((base, c) for c in group)
    for base, c in sorted(scoped, key=lambda pair: pair[1].claim_id):
        digest = hash_json(value=_assertion(c)).value.removeprefix("sha256:")
        name = f"{base}-scope-{digest[:16]}"
        while name in reserved:
            name = f"assertion-{name}"
        result[c.claim_id] = name
        reserved.add(name)
    return result
