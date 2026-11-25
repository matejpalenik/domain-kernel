"""Resolve legacy candidate edges against a separate, evidence-backed concept inventory."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.discovery.application.claim_extraction import (
    Anchor,
    LocatedMention,
    MentionInput,
    VerifiedAlias,
)
from domain_kernel.discovery.application.endpoint_contract import (
    REPAIR_VERSION,
    BindingEnvelope,
    EdgeBinding,
    EndpointReference,
)
from domain_kernel.discovery.application.evidence_binding import (
    exact_quote,
    identity_clauses,
    locate_mention,
)
from domain_kernel.shared.hashing import hash_json

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence

    from domain_kernel._shared.application.inference import InferenceInput
    from domain_kernel.discovery.application.claim_extraction import BatchResult, IdentifiedClaim
    from domain_kernel.discovery.application.claim_graph import ClaimGraph
    from domain_kernel.sources.domain.models import SourceRevision

_WORDS = re.compile(r"[^\W_]+")
_IDENT = re.compile(r"\b[a-z]{2,}[\u2013-][0-9]{2,}[a-z]?\b", re.IGNORECASE)
_CLAUSE = re.compile(r"[^.!?;\n]+(?:[.!?;]|$)")
_DECLARATION = re.compile(r"^I am (?:the|an?) (?P<role>[^.!?;,\n]+)", re.IGNORECASE)
_FIRST_PERSON = re.compile(r"\b(?:I|[Mm]e)\b")
_NAMED_IDENTITY = re.compile(
    r"\bare the same (?:application|system|entity|person|tool|record|referent),\s*(.+)",
    re.IGNORECASE,
)
_SHARED_NAMES = re.compile(
    r"""
    ^(?:the\ )?(?P<first>[\w -]+?)\ and\ (?:the\ )?(?P<second>[\w -]+?)
    \ are\ the\ same\ (?:application|system|entity|person|tool|record|referent),
    \s*(?P<referent>.+)$
    """,
    re.IGNORECASE | re.VERBOSE,
)
_MAX_CLAUSE_CONCEPTS = 16
_MIN_INFLECTED_LENGTH = 4
_UNASSERTED_IDENTITY = re.compile(
    r"""
    \b(?:alleg\w*|claim\w*|believ\w*|suspect\w*|assum\w*|hypothetic\w*|mistak\w*|
    reportedly|supposedly|rumou?r\w*|formerly|previously|used[ ]to|according[ ]to)\b|["\u201c\u201d]
    """,
    re.IGNORECASE | re.VERBOSE,
)
_CONTRARY_IDENTITY = re.compile(
    r"\b(?:different|distinct|separate|not the same|never the same)\b", re.IGNORECASE
)


def _words(text: str) -> str:
    return " ".join(_WORDS.findall(text.casefold()))


def _identifiers(text: str) -> set[str]:
    return {match[0].casefold().replace("\u2013", "-") for match in _IDENT.finditer(text)}


def _terms(*, name: str, title: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(term for text in (title, name) if (term := _words(text))))


def _number_variants(term: str) -> tuple[str, ...]:
    if len(term) < _MIN_INFLECTED_LENGTH or term[-1].isdigit():
        return (term,)
    if term.endswith("ies"):
        return (term, term[:-3] + "y")
    if term.endswith("s") and not term.endswith(("ss", "us", "is")):
        return (term, term[:-1])
    return (term, term + "s", term[:-1] + "ies") if term.endswith("y") else (term, term + "s")


def _find(*, text: str, term: str) -> str | None:
    """Find one occurrence, tolerating case, ordinary inflection and word separators."""
    parts = _WORDS.findall(term)
    if not parts:
        return None
    pattern = r"[\s\u2019'\u2013-]+".join(map(re.escape, parts))
    matches = list(re.finditer(rf"(?<!\w){pattern}(?!\w)", text, flags=re.IGNORECASE))
    return matches[0][0] if len(matches) == 1 else None


@dataclass(frozen=True, kw_only=True)
class _Concept:
    name: str
    terms: tuple[str, ...]
    identifiers: frozenset[str]
    sources: frozenset[SourceRevision]


class EndpointIndex:
    """Resolve candidate endpoint designations within one pinned evidence inventory."""

    def __init__(self, *, inputs: Sequence[InferenceInput]) -> None:
        """Index only the captured source passages supplied to this operation."""
        self.inputs: tuple[InferenceInput, ...] = tuple(inputs)
        self.clauses: tuple[Anchor, ...] = tuple(
            Anchor(citation=index, quote=match[0].strip())
            for index, part in enumerate(inputs, 1)
            for match in _CLAUSE.finditer(part.text)
            if match[0].strip()
        )
        self.narrators: tuple[tuple[Anchor, str], ...] = tuple(
            (anchor, _words(match["role"]))
            for anchor in self.clauses
            if (match := _DECLARATION.match(anchor.quote)) is not None
        )
        self.declarations: tuple[tuple[Anchor, str, str, str], ...] = tuple(
            (anchor, _words(match["first"]), _words(match["second"]), _words(match["referent"]))
            for anchor in self.clauses
            if (match := _SHARED_NAMES.fullmatch(anchor.quote)) is not None
            and any(
                identity_clauses(
                    quote=anchor.quote,
                    first=(_words(match["first"]),),
                    second=(_words(match["second"]),),
                )
            )
        )

    def part(self, index: int) -> InferenceInput:
        """Read one issued passage by its one-based reference."""
        return self.inputs[index - 1]

    def concepts(self, *, claims: Sequence[IdentifiedClaim]) -> dict[str, _Concept]:
        """Collect concept labels and identifiers genuinely present in their evidence."""
        return {
            claim.name: _Concept(
                name=claim.name,
                terms=_terms(name=claim.name, title=claim.title),
                identifiers=frozenset(
                    _identifiers(claim.title + " " + claim.name)
                    & {
                        value
                        for evidence in claim.evidence
                        for value in _identifiers(evidence.quote)
                    }
                ),
                sources=frozenset(
                    self.part(anchor.citation).evidence[0].source for anchor in claim.evidence
                ),
            )
            for claim in claims
        }

    def aliases(
        self, *, claims: Sequence[IdentifiedClaim], asserted_only: bool = False
    ) -> dict[str, VerifiedAlias]:
        """Resolve only compatible concepts joined by an explicit witnessed declaration."""
        candidates = {claim.name: claim for claim in claims}
        terms = self.concepts(claims=claims)
        pairs: dict[str, dict[str, Anchor]] = defaultdict(dict)
        for clause in self.clauses:
            if asserted_only and _UNASSERTED_IDENTITY.search(clause.quote):
                continue
            self._index_clause(clause=clause, terms=terms, pairs=pairs, asserted_only=asserted_only)
        conflicts = (
            self._identity_conflicts(terms=terms, names=pairs.keys()) if asserted_only else None
        )
        return _alias_groups(claims=candidates, concepts=terms, pairs=pairs, conflicts=conflicts)

    def _identity_conflicts(
        self, *, terms: Mapping[str, _Concept], names: Collection[str]
    ) -> set[frozenset[str]]:
        conflicts: set[frozenset[str]] = set()
        for clause in self.clauses:
            if not _CONTRARY_IDENTITY.search(clause.quote):
                continue
            text = f" {_words(clause.quote)} "
            source = self.part(clause.citation).evidence[0].source
            visible = [
                name
                for name in names
                if source in terms[name].sources
                and any(f" {term} " in text for term in terms[name].terms)
            ]
            conflicts.update(frozenset(pair) for pair in combinations(visible, 2))
        return conflicts

    def _index_clause(
        self,
        *,
        clause: Anchor,
        terms: Mapping[str, _Concept],
        pairs: dict[str, dict[str, Anchor]],
        asserted_only: bool,
    ) -> None:
        label = f" {_words(clause.quote)} "
        if not any(
            marker in label
            for marker in (
                " the same ",
                " known as ",
                " referred to as ",
                " called ",
                " name for ",
                " two names ",
            )
        ):
            return
        visible = [
            concept
            for concept in terms.values()
            if any(f" {term} " in label for term in concept.terms)
        ]
        if len(visible) > _MAX_CLAUSE_CONCEPTS:
            return
        for index, first in enumerate(visible):
            for second in visible[index + 1 :]:
                if asserted_only and not any(
                    label.startswith((f" {term} ", f" the {term} "))
                    for term in (*first.terms, *second.terms)
                ):
                    continue
                if any(
                    identity_clauses(quote=clause.quote, first=first.terms, second=second.terms)
                ):
                    self._link(first=first, second=second, clause=clause, pairs=pairs)
                    self._link_named_referent(
                        first=first, second=second, visible=visible, clause=clause, pairs=pairs
                    )

    def _link_named_referent(
        self,
        *,
        first: _Concept,
        second: _Concept,
        visible: Sequence[_Concept],
        clause: Anchor,
        pairs: dict[str, dict[str, Anchor]],
    ) -> None:
        tail = _NAMED_IDENTITY.search(clause.quote)
        if tail is None:
            return
        name = f" {_words(tail[1])} "
        referents = [
            item
            for item in visible
            if item.name not in {first.name, second.name}
            and any(f" {term} " in name for term in item.terms)
        ]
        if len(referents) == 1:
            self._link(first=first, second=referents[0], clause=clause, pairs=pairs)
            self._link(first=second, second=referents[0], clause=clause, pairs=pairs)

    def _link(
        self,
        *,
        first: _Concept,
        second: _Concept,
        clause: Anchor,
        pairs: dict[str, dict[str, Anchor]],
    ) -> None:
        source = self.part(clause.citation).evidence[0].source
        if source not in first.sources or source not in second.sources:
            return
        if (
            first.identifiers
            and second.identifiers
            and first.identifiers.isdisjoint(second.identifiers)
        ):
            return
        _ = pairs[first.name].setdefault(second.name, clause)
        _ = pairs[second.name].setdefault(first.name, clause)

    def _context(self, *, anchor: Anchor) -> tuple[Anchor, ...]:
        text = self.part(anchor.citation).text
        raw = exact_quote(text=text, quote=anchor.quote)
        if raw is None:
            return ()
        first = text.index(raw)
        return (
            Anchor(citation=anchor.citation, quote=raw),
            *(
                Anchor(citation=anchor.citation, quote=match[0].strip())
                for match in _CLAUSE.finditer(text)
                if match.start() <= first and first + len(raw) <= match.end()
            ),
        )

    def mention(self, *, concept: _Concept, evidence: Sequence[Anchor]) -> LocatedMention | None:
        """Find exact endpoint wording on the action evidence, including an explicit narrator."""
        for anchor in evidence:
            for region in self._context(anchor=anchor):
                located = self._direct_mention(concept=concept, region=region)
                if located is not None:
                    return located
                narrator = self._narrator_mention(concept=concept, region=region)
                if narrator is not None:
                    return narrator
                declared = self._declared_mention(concept=concept, region=region)
                if declared is not None:
                    return declared
        return None

    def _declared_mention(self, *, concept: _Concept, region: Anchor) -> LocatedMention | None:
        source = self.part(region.citation).evidence[0].source
        candidates = [
            (witness, word)
            for witness, first, second, referent in self.declarations
            if self.part(witness.citation).evidence[0].source == source
            and any(f" {term} " in f" {referent} " for term in concept.terms)
            for term in (first, second)
            if (word := _find(text=region.quote, term=term)) is not None
        ]
        if len(candidates) == 1:
            witness, word = candidates[0]
            return self._located(region=region, quote=word, identity=witness)
        return None

    def _direct_mention(self, *, concept: _Concept, region: Anchor) -> LocatedMention | None:
        ids = _identifiers(region.quote)
        terms = sorted(concept.identifiers) if ids and concept.identifiers else concept.terms
        for term in terms:
            for variant in _number_variants(term):
                if (quote := _find(text=region.quote, term=variant)) is not None and (
                    location := self._located(region=region, quote=quote)
                ) is not None:
                    return location
        return None

    def _narrator_mention(self, *, concept: _Concept, region: Anchor) -> LocatedMention | None:
        narrators = [
            (anchor, role) for anchor, role in self.narrators if anchor.citation == region.citation
        ]
        if len(narrators) != 1:
            return None
        witness, role = narrators[0]
        if role not in concept.terms:
            return None
        pronouns = [match[0] for match in _FIRST_PERSON.finditer(region.quote)]
        if len(pronouns) != 1:
            return None
        return self._located(region=region, quote=pronouns[0], identity=witness)

    def _located(
        self, *, region: Anchor, quote: str, identity: Anchor | None = None
    ) -> LocatedMention | None:
        value = locate_mention(
            mention=MentionInput(
                ref="endpoint",
                anchor=Anchor(citation=region.citation, quote=quote),
                context=region.quote,
                role=None,
                approved_name=None,
            ),
            index=region.citation,
            part=self.part,
            canonical=(),
            approved=set(),
        )
        return (
            value.model_copy(update={"identity_witness": identity}) if value and identity else value
        )


def _alias_groups(
    *,
    claims: Mapping[str, IdentifiedClaim],
    concepts: Mapping[str, _Concept],
    pairs: Mapping[str, Mapping[str, Anchor]],
    conflicts: set[frozenset[str]] | None,
) -> dict[str, VerifiedAlias]:
    aliases: dict[str, VerifiedAlias] = {}
    retained: set[str] = set()
    for preferred in sorted(pairs, key=lambda key: (-bool(concepts[key].identifiers), key)):
        if preferred in aliases:
            continue
        retained.add(preferred)
        joined = {preferred}
        identifiers = set(concepts[preferred].identifiers)
        for name, witness in sorted(pairs[preferred].items()):
            old, new = claims[name], claims[preferred]
            if conflicts is not None and (
                any(frozenset((name, member)) in conflicts for member in joined)
                or len(identifiers | concepts[name].identifiers) > 1
            ):
                continue
            if (
                name not in retained
                and name not in aliases
                and [q.text for q in old.conditions] == [q.text for q in new.conditions]
                and [q.text for q in old.exceptions] == [q.text for q in new.exceptions]
            ):
                aliases[name] = VerifiedAlias(
                    alternate=name,
                    preferred=preferred,
                    alternate_quote=old.evidence[0].quote,
                    preferred_quote=new.evidence[0].quote,
                    reason=(
                        "The source explicitly identifies both designations as the same referent."
                    ),
                    identity_witness=witness,
                )
                joined.add(name)
                identifiers.update(concepts[name].identifiers)
    return aliases


def _key(*, claim: IdentifiedClaim, index: EndpointIndex) -> str:
    evidence = index.part(claim.evidence[0].citation).evidence[0]
    digest = hash_json(value=record_value(value=(evidence.source, claim.name, claim.claim_id)))
    return "entity-" + digest.value.removeprefix("sha256:")


@dataclass(frozen=True, kw_only=True)
class RepairProjection:
    """Final SDK rows and their independent concept identity handoff."""

    rows: list[IdentifiedClaim]
    binding: BindingEnvelope


def project(  # noqa: PLR0913 - The projection binds the exact graph and capture.
    *,
    graph: ClaimGraph,
    accepted_rows: Sequence[IdentifiedClaim],
    batches: Sequence[BatchResult],
    names: Mapping[str, str],
    index: EndpointIndex,
    aliases: Mapping[str, VerifiedAlias],
) -> RepairProjection:
    """Serialize validated concept bindings and retain unresolved action occurrences."""
    originals = {
        claim.claim_id: claim for batch in batches for claim in (*batch.candidates, *batch.accepted)
    }
    known = index.concepts(
        claims=[claim for claim in originals.values() if claim.kind == "concept"]
    )
    concepts = [claim for claim in accepted_rows if claim.kind == "concept"]
    counts = Counter(claim.name for claim in concepts)
    keys = {
        claim.name: _key(claim=claim, index=index) for claim in concepts if counts[claim.name] == 1
    }
    exported = {_key(claim=claim, index=index): names[claim.claim_id] for claim in concepts}
    claimed: set[str] = set()
    rows = list(concepts)
    edges: list[EdgeBinding] = []
    for claim in accepted_rows:
        if claim.kind != "relationship":
            continue
        origins = graph.origins[claim.claim_id]
        original = originals.get(claim.claim_id, claim)
        edge = _project_edge(
            claim=claim,
            original=original,
            proposal_name=names[claim.claim_id],
            index=index,
            concepts=known,
            keys=keys,
            aliases=aliases,
            origins=origins,
        )
        edges.append(edge)
        if edge.proposal_name is not None:
            rows.append(claim)
        claimed.update(origins)
    reasons = {finding.claim_id: finding.detail for finding in graph.findings}
    edges.extend(
        EdgeBinding(
            claim_id=claim.claim_id,
            proposal_name=None,
            source=None,
            target=None,
            evidence=claim.evidence,
            identity_evidence=[],
            origin_claim_ids=[claim.claim_id],
            reason=reasons.get(
                claim.claim_id, "Review the evidence for the proposed directed edge."
            ),
        )
        for claim in originals.values()
        if claim.kind == "relationship" and claim.claim_id not in claimed
    )
    return RepairProjection(
        rows=rows,
        binding=BindingEnvelope(contract=REPAIR_VERSION, concepts=exported, edges=edges),
    )


def _project_edge(  # noqa: PLR0913 - Keep original and canonical endpoints attributable.
    *,
    claim: IdentifiedClaim,
    original: IdentifiedClaim,
    proposal_name: str,
    index: EndpointIndex,
    concepts: Mapping[str, _Concept],
    keys: Mapping[str, str],
    aliases: Mapping[str, VerifiedAlias],
    origins: list[str],
) -> EdgeBinding:
    identity: list[Anchor] = []

    def endpoint(*, observed: str | None, canonical: str | None) -> EndpointReference | None:
        if canonical is None or observed is None:
            return None
        concept = concepts.get(observed)
        if (
            concept is None
            or (occurrence := index.mention(concept=concept, evidence=original.evidence)) is None
        ):
            return None
        if occurrence.identity_witness is not None:
            identity.append(occurrence.identity_witness)
        if observed != canonical and (alias := aliases.get(observed)) is not None:
            identity.append(alias.identity_witness)
        return EndpointReference(occurrence=occurrence, concept_key=keys.get(canonical))

    source = endpoint(observed=original.source, canonical=claim.source)
    target = endpoint(observed=original.target, canonical=claim.target)
    resolved = all(endpoint is not None and endpoint.concept_key for endpoint in (source, target))
    return EdgeBinding(
        claim_id=claim.claim_id,
        proposal_name=proposal_name if resolved else None,
        source=source,
        target=target,
        evidence=claim.evidence,
        identity_evidence=identity,
        origin_claim_ids=origins,
        reason=None
        if resolved
        else "The exact endpoint occurrence or concept could not be resolved.",
    )
