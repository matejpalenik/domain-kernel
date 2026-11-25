"""Flag possible qualifier loss against cited prose without changing a proposal."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.discovery.application import scope_corroboration
from domain_kernel.discovery.application.claim_extraction import BoundClaim, normalized
from domain_kernel.discovery.application.held_endpoints import containing_span

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from domain_kernel._shared.application.inference import InferenceInput
    from domain_kernel.discovery.application.claim_extraction import Anchor, IdentifiedClaim


VERSION = "scope-shadow-v3"
_Kind = Literal["means", "modality", "negation", "condition", "exception", "concession"]
_SENTENCE_BREAK = re.compile(r"[.!?](?=\s)|\n")
_WORD = re.compile(r"[^\W\d_]+")
_BY_ACTION = r"by\s+(?:\w+ly\s+){0,2}(?P<verb>\w+ing)\b"
_MEANS = re.compile(rf"^{_BY_ACTION}(?P<detail>[^,]+),", re.IGNORECASE)
_CLAIM_MEANS = re.compile(rf"\b{_BY_ACTION}(?P<detail>[^,.;!?]*)", re.IGNORECASE)
_MEANS_FILLER = frozenset({"a", "an", "the", "this", "these", "those", "to", "of", "with"})
_MODALS = r"can|could|may|might|must|shall|should|(?:is|are) (?:allowed|required|permitted) to"
_NEGATION = r"not(?!\s+only\b)|never|no longer|cannot|can['\u2019]t|doesn['\u2019]t|don['\u2019]t"
_FORCE = rf"(?:(?:{_MODALS})\s+)?(?P<negation>{_NEGATION})|(?P<modality>{_MODALS})"
_PREDICATE = re.compile(
    rf"\b(?:{_FORCE})\s+(?:(?:better|still|also|always|ever|only|usually)\s+)*(?P<verb>[^\W\d_]+)",
    re.IGNORECASE,
)
_EXCEPTION = r"unless|except\s+(?:if|when|for)"
_CONDITION = r"if|provided\s+that|as\s+long\s+as|only\s+when|^(?:after|before|during|when)"
_CONCESSION = r"although|despite|even\s+though"
_CONTEXT = re.compile(
    rf"\b(?:(?P<exception>{_EXCEPTION})|(?P<condition>{_CONDITION})|(?P<concession>{_CONCESSION}))\b",
    re.IGNORECASE,
)
_PRESENT_RELATIVE = re.compile(
    r"\b(?:that|which|who)\s+(?P<predicate>[^,;.!?]*?\b(?:today|now|currently))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, kw_only=True, slots=True)
class ScopeFinding:
    """A lexical warning with the original sentence and its issued citation."""

    claim_id: str
    kind: _Kind
    citation: int
    quote: str
    cue: str


@dataclass(frozen=True, kw_only=True, slots=True)
class ScopeCorroboration:
    """A warning cleared by another exact quote in the same cited passage."""

    finding: ScopeFinding
    corroborating_quote: str


@dataclass(frozen=True, kw_only=True, slots=True)
class ScopeAudit:
    """Counts and review findings for the versioned observation policy."""

    version: str
    relationships_checked: int
    findings: tuple[ScopeFinding, ...]
    corroborations: tuple[ScopeCorroboration, ...]


def _verb_stems(word: str) -> set[str]:
    stems = {word}
    if (stem := word.removesuffix("ing")) != word and len(stem) > 1:
        stems.update((stem, stem + "e"))
        if stem[-1] == stem[-2]:
            stems.add(stem[:-1])
    if word.endswith("es"):
        stems.add(word[:-2])
    if word.endswith("s"):
        stems.add(word[:-1])
    return stems


def _means_terms(detail: str) -> set[str]:
    return {word[0] for word in _WORD.finditer(detail.casefold())} - _MEANS_FILLER


def _retains_paraphrased_means(*, sentence: str, means: re.Match[str], wording: str) -> bool:
    """Compare the means and its distinct modal outcome across both clauses."""
    outcome = _PREDICATE.search(sentence, pos=means.end())
    terms = _means_terms(means["detail"])
    if outcome is None or not outcome["modality"] or not terms:
        return False
    for phrase in _CLAIM_MEANS.finditer(wording):
        if phrase["verb"] != means["verb"].casefold() or not terms <= _means_terms(
            phrase["detail"]
        ):
            continue
        other_clause = wording[phrase.end() :] if phrase.start() == 0 else wording[: phrase.start()]
        if any(
            match["modality"] == outcome["modality"].casefold()
            and match["verb"] == outcome["verb"].casefold()
            for match in _PREDICATE.finditer(other_clause)
        ):
            return True
    return False


def _predicate_cues(
    *, sentence: str, anchor: re.Match[str], wording: str, qualifications: str
) -> Iterator[tuple[_Kind, str]]:
    words = {stem for word in _WORD.finditer(wording) for stem in _verb_stems(word[0])}
    means = _MEANS.match(sentence)
    if means and anchor.start() < means.end() and _verb_stems(means["verb"].lower()) & words:
        cue = means[0][:-1]
        if normalized(cue).casefold() not in qualifications and not _retains_paraphrased_means(
            sentence=sentence, means=means, wording=wording
        ):
            yield "means", cue
    for match in _PREDICATE.finditer(sentence):
        verb = match["verb"].lower()
        if (
            not _verb_stems(verb) & words
            or anchor.end() <= match.start()
            or anchor.start() >= match.end()
        ):
            continue
        if cue := match["negation"]:
            if not re.search(rf"\b(?:{_NEGATION})\b", wording):
                yield "negation", cue
        elif not re.search(rf"\b{re.escape(match['modality'].lower())}\b", wording):
            yield "modality", match["modality"]


def _context_cues(
    *, sentence: str, anchor: re.Match[str], wording: str, qualifications: str
) -> Iterator[tuple[_Kind, str]]:
    for match in _CONTEXT.finditer(sentence):
        end = sentence.find(",", match.end()) if match.start() == 0 else len(sentence)
        if end < 0 or (match.start() == 0 and anchor.end() <= end):
            continue
        if match[0].casefold() == "during" and _asserts_present_predicate(
            evidence=anchor[0], wording=wording
        ):
            continue
        cue = sentence[match.start() : end].rstrip(".!? ")
        if normalized(cue).casefold() in qualifications:
            continue
        if match["exception"]:
            yield "exception", cue
        elif match["concession"]:
            yield "concession", cue
        else:
            yield "condition", cue


def _asserts_present_predicate(*, evidence: str, wording: str) -> bool:
    """Recognize a directly asserted, independently timed relative predicate."""
    relative = _PRESENT_RELATIVE.search(evidence)
    if relative is None or _PRESENT_RELATIVE.search(wording):
        return False
    predicate = normalized(relative["predicate"]).casefold()
    return wording.rstrip(".!?").endswith(f" {predicate}")


def _cited_sentence(
    *, anchor: Anchor, inputs: Sequence[InferenceInput], cache: dict[tuple[int, str], str | None]
) -> str | None:
    if not 1 <= anchor.citation <= len(inputs):
        return None
    part = inputs[anchor.citation - 1]
    key = (anchor.citation, anchor.quote)
    if key not in cache:
        quote = (
            containing_span(text=part.text, quote=anchor.quote, row=False)
            if not part.is_table and anchor.quote.strip()
            else None
        )
        cache[key] = quote if quote and not _SENTENCE_BREAK.search(quote) else None
    return cache[key]


def inspect(*, rows: Sequence[IdentifiedClaim], inputs: Sequence[InferenceInput]) -> ScopeAudit:
    """Inspect one uniquely reopenable sentence per anchor and keep one flag per kind."""
    cache: dict[tuple[int, str], str | None] = {}
    findings: dict[tuple[str, _Kind], ScopeFinding] = {}
    corroborations: dict[tuple[str, _Kind], ScopeCorroboration] = {}
    checked = 0
    for claim in rows:
        if claim.kind != "relationship":
            continue
        modality = (claim.modality or "") if isinstance(claim, BoundClaim) else ""
        wording = normalized(f"{claim.meaning} {modality}").casefold()
        qualifications = normalized(
            " ".join((wording, *(q.text for q in (*claim.conditions, *claim.exceptions))))
        ).casefold()
        resolved = False
        for anchor in claim.evidence:
            quote = _cited_sentence(anchor=anchor, inputs=inputs, cache=cache)
            if quote is None:
                continue
            evidence = re.search(r"\s+".join(map(re.escape, anchor.quote.split())), quote)
            if evidence is None:
                continue
            resolved = True
            cues = (
                *_predicate_cues(
                    sentence=quote, anchor=evidence, wording=wording, qualifications=qualifications
                ),
                *_context_cues(
                    sentence=quote, anchor=evidence, wording=wording, qualifications=qualifications
                ),
            )
            for kind, cue in cues:
                key = (claim.claim_id, kind)
                if key in findings:
                    continue
                finding = ScopeFinding(
                    claim_id=claim.claim_id,
                    kind=kind,
                    citation=anchor.citation,
                    quote=quote,
                    cue=cue,
                )
                witness = scope_corroboration.witness(
                    claim=claim,
                    sentence=quote,
                    cue=cue,
                    source_text=inputs[anchor.citation - 1].text,
                    evidence=evidence[0],
                )
                if witness is None:
                    findings[key] = finding
                else:
                    _ = corroborations.setdefault(
                        key, ScopeCorroboration(finding=finding, corroborating_quote=witness)
                    )
        checked += resolved
    return ScopeAudit(
        version=VERSION,
        relationships_checked=checked,
        findings=tuple(findings.values()),
        corroborations=tuple(item for key, item in corroborations.items() if key not in findings),
    )
