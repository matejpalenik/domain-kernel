"""Bind extracted participant references to verified locations before graph assembly."""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from domain_kernel.discovery.application.claim_extraction import (
    Anchor,
    BoundClaim,
    BoundRepair,
    LinkedQualifier,
    LocatedMention,
    Qualification,
    normalized,
)
from domain_kernel.shared.domain.codecs.record_encoding import record_value
from domain_kernel.shared.hashing import hash_json
from domain_kernel.sources.domain.parsed import DocumentSpan

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from domain_kernel.discovery.application.claim_extraction import (
        BoundDraft,
        IdentifiedClaim,
        MentionInput,
    )
    from domain_kernel.shared.application.inference import InferenceInput


VERSION = "evidence-bound-v1"
MINING = (
    "Return the claims and batch-local mention table required by the schema. Each mention "
    "has a unique ref, the exact source words in anchor, and a longer exact context from "
    "the same passage when the mention recurs. Use null for unknown role or approved_name. "
    "Use an approved_name only if the passage identifies that approved concept in the same "
    "sense. A concept sets mention to its own mention ref and source and target to null. "
    "A relationship sets source and target to mention refs and mention to null. Give each "
    "participant a concept claim when it is supported and has no approved match. Capture "
    "each coordinated recipient or action in a distinct directed relationship. Preserve "
    "the intended use, obligation, permission, or other modality as stated. Give each "
    "qualifier its own ref and exact evidence. Use applies_to=null for the claim or another "
    "qualifier's ref for nested scope. An override must point to the exception it limits. "
    "Keep references to other clauses in the exact claim or qualification evidence. "
    "These schema and reference rules supersede any earlier endpoint naming instructions. "
)
CHECK = (
    " The subject and object metadata identify exact cited occurrences and contextual roles. "
    "Check those participants and the stated modality, including any approved definition "
    "named in the metadata. In qualifiers, applies_to identifies the parent qualifier, or "
    "the claim when null. Preserve the scope of each exception and override. "
)


def annex_references(text: str) -> set[str]:
    """Recognize explicit Roman-numbered annex headings."""
    return set(re.findall(r"\bannex [ivxlcdm]+\b", text.casefold()))


def _spans(text: str, quote: str) -> Iterable[tuple[int, int]]:
    tokens = quote.split()
    if not tokens:
        return
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    if re.match(r"\w", tokens[0]):
        pattern = r"(?<!\w)" + pattern
    if re.search(r"\w$", tokens[-1]):
        pattern += r"(?!\w)"
    # Include overlapping occurrences when deciding if a witness identifies a unique span.
    yield from (match.span(1) for match in re.finditer(f"(?=({pattern}))", text))


def _span(text: str, quote: str, context: str | None) -> tuple[int, int] | None:
    if context is None:
        matches = list(_spans(text, quote))
    else:
        matches = [
            (start + first, start + last)
            for start, end in _spans(text, context)
            for first, last in _spans(text[start:end], quote)
        ]
    exact = set(matches)
    return next(iter(exact)) if len(exact) == 1 else None


def locate_mention(  # noqa: PLR0913 - Resolution needs the passage and its captured alternatives.
    *,
    mention: MentionInput,
    index: int,
    part: Callable[[int], InferenceInput],
    canonical: Iterable[int],
    approved: set[str],
    require_unique_source: bool = False,
) -> LocatedMention | None:
    """Use canonical page offsets only when their occurrence is unambiguous."""
    resolved = _span(part(index).text, mention.anchor.quote, mention.context)
    if resolved is None:
        return None
    alternatives = [
        (i, span)
        for i in dict.fromkeys(canonical)
        if (span := _span(part(i).text, mention.anchor.quote, mention.context)) is not None
    ]
    if len(alternatives) == 1:
        index, resolved = alternatives[0]
    elif require_unique_source and alternatives:
        return None
    first, last = resolved
    passage = part(index)
    evidence = passage.evidence[0]
    source, locator = evidence.source, evidence.locator
    location: object = (locator, first, last)
    if isinstance(locator, DocumentSpan):
        location = (locator.page, locator.section, locator.start + first, locator.start + last)
    digest = hash_json(
        value=record_value(
            value=(source.project_id, source.source_id, source.revision_id, location),
        )
    ).value.removeprefix("sha256:")
    name = mention.approved_name
    if name not in approved:
        name = None
    return LocatedMention(
        id=f"m-{digest[:24]}",
        anchor=Anchor(citation=index, quote=passage.text[first:last]),
        start=first,
        end=last,
        role=mention.role,
        approved_name=name,
    )


def qualifier_paths(qualifiers: Sequence[LinkedQualifier]) -> tuple[tuple[str, ...], ...] | None:
    """Validate parent references and compare qualification trees independently of model IDs."""
    by_ref = {q.ref: q for q in qualifiers}
    if len(by_ref) != len(qualifiers) or any(
        not q.ref.strip() or not q.text.strip() for q in qualifiers
    ):
        return None
    paths: list[tuple[str, ...]] = []
    for q in qualifiers:
        if q.kind == "override":
            parent = by_ref.get(q.applies_to or "")
            if parent is None or parent.kind != "exception":
                return None
        seen: set[str] = set()
        path: list[tuple[str, str]] = []
        current = q
        while True:
            if current.ref in seen:
                return None
            seen.add(current.ref)
            path.append((current.kind, normalized(current.text)))
            if current.applies_to is None:
                break
            parent = by_ref.get(current.applies_to)
            if parent is None:
                return None
            current = parent
        paths.append(tuple(value for step in reversed(path) for value in step))
    return tuple(sorted(paths))


def bind_claim(  # noqa: PLR0913 - Bind a row to the original passage inventory and identity.
    *,
    row: BoundDraft,
    mentions: Mapping[str, LocatedMention],
    indexes: list[int],
    resolve: Callable[[Anchor, list[int]], Anchor | None],
    identify: Callable[[BoundClaim], IdentifiedClaim],
    include_participant_evidence: bool = True,
) -> BoundClaim | None:
    """Admit only supported locations and well-formed participant references."""
    if (
        qualifier_paths(row.qualifiers) is None
        or not row.evidence
        or not row.title.strip()
        or not row.meaning.strip()
    ):
        return None
    subject, target = mentions.get(row.source or ""), mentions.get(row.target or "")
    concept = mentions.get(row.mention or "")
    if row.kind == "relationship" and (
        subject is None or target is None or row.mention is not None
    ):
        return None
    if row.kind == "concept" and (
        concept is None or row.source is not None or row.target is not None
    ):
        return None
    support = _resolve_support(row=row, indexes=indexes, resolve=resolve)
    if support is None:
        return None
    anchors, qualifiers = support
    if include_participant_evidence:
        for mention in (concept, subject, target):
            if mention is not None and mention.anchor not in anchors:
                anchors.append(mention.anchor)
    claim = BoundClaim(
        claim_id=row.claim_id if isinstance(row, BoundRepair) else "",
        kind=row.kind,
        preferred_name=row.name,
        name=row.name if concept is None else concept.id,
        title=row.title,
        meaning=row.meaning,
        evidence=anchors,
        mention=concept,
        subject=subject,
        object=target,
        modality=row.modality,
        qualifiers=qualifiers,
        source=subject.endpoint if subject else None,
        target=target.endpoint if target else None,
        conditions=[
            Qualification(text=q.text, evidence=q.evidence)
            for q in qualifiers
            if q.kind == "condition"
        ],
        exceptions=[
            Qualification(text=q.text, evidence=q.evidence)
            for q in qualifiers
            if q.kind != "condition"
        ],
    )
    if not claim.claim_id:
        claim.claim_id = identify(claim).claim_id
    return claim


def supports_mention(
    *, mention: LocatedMention, anchors: Sequence[Anchor], part: Callable[[int], InferenceInput]
) -> bool:
    """Find the bound character span inside the supporting quotations."""
    index = mention.anchor.citation
    text = part(index).text
    return any(
        start <= mention.start and mention.end <= end
        for anchor in anchors
        if anchor.citation == index
        for start, end in _spans(text, anchor.quote)
    )


def exact_quote(*, text: str, quote: str) -> str | None:
    """Recover the original wording and whitespace of a uniquely located quotation."""
    span = _span(text, quote, None)
    return text[span[0] : span[1]] if span is not None else None


_QUALIFIED_IDENTITY = re.compile(
    r"""\b(
    not|never|if|unless|could|may|might|whether|different|distinct|false|
    type|kind|category|role|class|group|family|capability|pattern|purpose|separately|respectively
    )\b""",
    flags=re.IGNORECASE | re.VERBOSE,
)
_SAME_REFERENT = r"the same (application|system|entity|person|tool|record|referent)"


def _identity_pair(*, text: str, first: str, second: str) -> bool:
    left, right = re.escape(first), re.escape(second)
    alias = r"(?:is )?(?:also (?:known as|referred to as|called)|another name for)"
    coordinated = rf"\b{left} and (?:the )?{right} "
    same = rf"are (?:both )?{_SAME_REFERENT}"
    refers = rf"(?:both )?refer to {_SAME_REFERENT}"
    identifier_type = r"(?:application|system|record) id(?:entifier)?"
    identifier = rf"(?:have|share|are assigned) the same (?:unique )?{identifier_type}"
    connects = rf"(?:{same}|{refers}|are two names for|(?:both )?{identifier})\b"
    return any(
        re.search(pattern, text) is not None
        for pattern in (
            rf"\b{left} {alias} (?:the )?{right}\b",
            rf"\b{left} is {_SAME_REFERENT} as (?:the )?{right}\b",
            coordinated + connects,
        )
    )


def identity_clauses(*, quote: str, first: Sequence[str], second: Sequence[str]) -> Iterable[str]:
    """Recognize explicit identity statements directly connecting the two designations."""
    pairs = {(a, b) for a in first for b in second if a and b and a != b}
    for clause in re.split(r"[.!?;\n]+", quote):
        if _QUALIFIED_IDENTITY.search(clause):
            continue
        text = " ".join(re.findall(r"[^\W_]+", clause.casefold()))
        if any(
            _identity_pair(text=text, first=a, second=b)
            or _identity_pair(text=text, first=b, second=a)
            for a, b in sorted(pairs)
        ):
            yield clause


def _resolve_support(
    *,
    row: BoundDraft,
    indexes: list[int],
    resolve: Callable[[Anchor, list[int]], Anchor | None],
) -> tuple[list[Anchor], list[LinkedQualifier]] | None:
    groups: list[list[Anchor]] = []
    for quoted in (row, *row.qualifiers):
        resolved = [resolve(a, indexes) for a in quoted.evidence]
        if not resolved or any(a is None for a in resolved):
            return None
        groups.append([a for a in resolved if a is not None])
    return groups[0], [
        q.model_copy(update={"evidence": anchors})
        for q, anchors in zip(row.qualifiers, groups[1:], strict=True)
    ]


def project_claims(
    *,
    rows: Sequence[IdentifiedClaim],
    approved: set[str],
) -> list[IdentifiedClaim]:
    """Translate assembly identities to the existing public lookup-name contract."""
    concepts = [row for row in rows if isinstance(row, BoundClaim) and row.kind == "concept"]
    counts = Counter(c.preferred_name for c in concepts)
    aliases: dict[str, str] = {}
    reserved = approved | {row.name for row in rows if row.kind == "relationship"}
    for c in sorted(concepts, key=lambda item: (counts[item.preferred_name], item.name)):
        base = c.preferred_name
        key = base
        if counts[base] > 1 or key in reserved:
            key = f"{base}-scope-{c.name.removeprefix('m-')}"
            while key in reserved:
                key = f"concept-{key}"
        aliases[c.name] = key
        reserved.add(key)
    return [
        c.model_copy(
            update={
                "name": aliases.get(c.name, c.name),
                "source": aliases.get(c.source, c.source) if c.source else None,
                "target": aliases.get(c.target, c.target) if c.target else None,
            }
        )
        for c in rows
    ]


def coverage_claim(claim: BoundClaim) -> dict[str, object]:
    """Present existing participants and qualification structure to omission review."""
    return {
        "name": claim.preferred_name,
        "meaning": claim.meaning,
        "source": claim.subject.anchor.quote if claim.subject else None,
        "target": claim.object.anchor.quote if claim.object else None,
        "modality": claim.modality,
        "qualifiers": [q.model_dump(exclude={"evidence"}) for q in claim.qualifiers],
    }


def qualified_meaning(claim: BoundClaim) -> str:
    """Render nested qualifications in the current proposal's meaning field."""
    by_ref = {q.ref: q for q in claim.qualifiers}
    clauses = [claim.meaning]
    if claim.modality:
        clauses.append(f"Modality: {claim.modality}.")
    for q in claim.qualifiers:
        parent = by_ref.get(q.applies_to or "")
        scope = f' of "{parent.text}"' if parent is not None else ""
        clauses.append(f"{q.kind.capitalize()}{scope}: {q.text}")
    return " ".join(clauses)
