"""Bind verified continuation edges to explicit occurrences in their cited prose."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from domain_kernel.discovery.application import evidence_binding, held_endpoints
from domain_kernel.discovery.application.claim_extraction import (
    Anchor,
    IdentifiedClaim,
    MentionInput,
)
from domain_kernel.discovery.application.claim_graph import AMBIGUOUS_ENDPOINT, proposal_names

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.application.inference import InferenceInput
    from domain_kernel.discovery.application.claim_extraction import LocatedMention
    from domain_kernel.discovery.application.claim_graph import ClaimGraph


_SENTENCE_BREAK = re.compile(r"[.!?](?=\s)|\n")


def _role_words(*, text: str, source: str, target: str) -> tuple[str, str] | None:
    matches: list[re.Match[str]] = []
    for name in (source, target):
        phrase = r"[-\s]+".join(re.escape(word) for word in name.split("-"))
        found = list(re.finditer(rf"(?<!\w){phrase}(?!\w)", text, flags=re.IGNORECASE))
        if len(found) != 1:
            return None
        matches.append(found[0])
    subject, obj = matches
    if subject.end() > obj.start():
        return None
    # A purpose clause describes an opportunity for a participant to act.
    before, after = text[: subject.start()], text[subject.end() :]
    if re.search(r"\bfor\s+$", before, flags=re.IGNORECASE) and re.match(
        r"\s+to\b", after, flags=re.IGNORECASE
    ):
        return None
    return subject[0], obj[0]


def _participants(
    *, claim: IdentifiedClaim, inputs: Sequence[InferenceInput]
) -> tuple[Anchor, LocatedMention, LocatedMention] | None:
    source, target = claim.source, claim.target
    if (
        not source
        or not target
        or _role_words(text=claim.meaning, source=source, target=target) is None
    ):
        return None
    witnesses: dict[tuple[int, str], tuple[str, str]] = {}
    for anchor in claim.evidence:
        part = inputs[anchor.citation - 1]
        if part.is_table:
            continue
        excerpt = held_endpoints.containing_span(text=part.text, quote=anchor.quote, row=False)
        if excerpt is None or _SENTENCE_BREAK.search(excerpt):
            continue
        roles = _role_words(text=excerpt, source=source, target=target)
        if roles is not None:
            witnesses[(anchor.citation, excerpt)] = roles
    if len(witnesses) != 1:
        return None
    (((citation, sentence), roles),) = witnesses.items()
    located = [
        evidence_binding.locate_mention(
            mention=MentionInput(
                ref=word,
                anchor=Anchor(citation=citation, quote=word),
                context=sentence,
                role=None,
                approved_name=None,
            ),
            index=citation,
            part=lambda index: inputs[index - 1],
            canonical=(),
            approved=set(),
        )
        for word in roles
    ]
    first, second = located
    if first is None or second is None:
        return None
    return Anchor(citation=citation, quote=sentence), first, second


def _witnesses(*, concept: IdentifiedClaim, mention: LocatedMention, text: str) -> bool:
    for anchor in concept.evidence:
        if anchor.citation != mention.anchor.citation:
            continue
        start = text.find(anchor.quote)
        if (
            0 <= start <= mention.start < mention.end <= start + len(anchor.quote)
            and text.find(anchor.quote, start + 1) == -1
        ):
            return True
    return False


def _occurrence(*, name: str, mention: LocatedMention, sentence: Anchor) -> IdentifiedClaim:
    return IdentifiedClaim(
        claim_id=mention.id,
        kind="concept",
        name=f"{name}-occurrence-{mention.id.removeprefix('m-')}",
        title=mention.anchor.quote,
        meaning=sentence.quote,
        source=None,
        target=None,
        evidence=[mention.anchor, sentence],
        conditions=[],
        exceptions=[],
    )


def recover(
    *,
    graph: ClaimGraph,
    held: Sequence[held_endpoints.HeldClaim],
    inputs: Sequence[InferenceInput],
    reserved: set[str],
) -> list[held_endpoints.RecoveredEdge]:
    """Retain the verified assertion and disambiguate its ordered, witnessed roles."""
    concepts: dict[str, list[IdentifiedClaim]] = defaultdict(list)
    names = proposal_names(claims=graph.claims)
    for row in graph.claims:
        if row.kind == "concept":
            concepts[row.name].append(row)
    proposals: list[held_endpoints.RecoveredEdge] = []
    for item in held:
        claim = item.claim
        if item.reason != AMBIGUOUS_ENDPOINT or claim.source is None or claim.target is None:
            continue
        participants = _participants(claim=claim, inputs=inputs)
        if participants is None:
            continue
        sentence, source, target = participants
        text = inputs[sentence.citation - 1].text
        matches = [
            [row for row in concepts[name] if _witnesses(concept=row, mention=mention, text=text)]
            for name, mention in ((claim.source, source), (claim.target, target))
        ]
        # At least one role needs an existing, uniquely witnessed concept. An
        # ambiguous formulation at the same occurrence still needs review.
        if not any(matches) or any(len(rows) > 1 for rows in matches):
            continue
        endpoints: list[IdentifiedClaim] = []
        created: list[IdentifiedClaim] = []
        for name, mention, rows in zip(
            (claim.source, claim.target), (source, target), matches, strict=True
        ):
            if rows and names[rows[0].claim_id] not in reserved:
                endpoint = rows[0].model_copy(update={"name": names[rows[0].claim_id]})
            else:
                endpoint = _occurrence(name=name, mention=mention, sentence=sentence)
                created.append(endpoint)
            endpoints.append(endpoint)
        if any(row.name in reserved for row in created):
            continue
        first, second = endpoints
        edge = claim.model_copy(
            update={
                "source": first.name,
                "target": second.name,
                "evidence": list(
                    {
                        (a.citation, a.quote): a
                        for a in (*claim.evidence, sentence, source.anchor, target.anchor)
                    }.values()
                ),
            }
        )
        proposals.append(
            held_endpoints.RecoveredEdge(
                edge=edge,
                concepts=created,
                source_meaning=first.meaning,
                target_meaning=second.meaning,
            )
        )
    return held_endpoints.admit(graph=graph, repaired=proposals)
