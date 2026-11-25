"""Check whether a local scope warning has independent nearby source support."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from domain_kernel.discovery.application.claim_extraction import normalized

if TYPE_CHECKING:
    from domain_kernel.discovery.application.claim_extraction import IdentifiedClaim


_NEIGHBOR_LIMIT = 1024
_PARAGRAPH_BREAK = re.compile(r"\n[ \t\r]*\n")
_SENTENCE_BOUNDARY = re.compile(r"[.!?](?=\s)|\n")
_QUALIFIED = re.compile(
    r"\b(?:if|unless|except|when|only|may|might|could|can|would|should|must|not|never|cannot)\b"
)
_PRACTITIONER = re.compile(r"(?P<topic>.+) (?:artist|practitioner|enthusiast)s?$")
_ADJUST = r"(?:prune|trim|cut|adjust)s?"
_ADJUSTMENT = re.compile(rf"^(?P<actor>[^,.;!?]+?)\s+(?:\w+ly\s+)?{_ADJUST}\b")
_DIMENSION = r"size|height|length|width|volume"
_DIMENSION_PURPOSE = re.compile(
    rf"\bto (?:maintain|limit|regulate|keep) (?:its|their) (?:\w+ )?(?:{_DIMENSION})\b"
)
_CONTROL_GROWTH = re.compile(r"\b(?:control|limit|regulate)s?\b[^.;!?]*\bgrowth\b")
_TRANSPORT = {"transmitted": "transmits?", "carried": "carr(?:y|ies)", "relayed": "relays?"}
_PASSIVE = "|".join(_TRANSPORT)
_SIGNAL_MEDIUM = r"(?:signal|signaling|communication) (?:line|channel|path|link)"
_CHANNEL_ROLE = rf"(?:serves as|acts as|functions as|is) (?:a |an |the )?{_SIGNAL_MEDIUM}"


def _previous_sentence(*, text: str, sentence: str) -> str | None:
    head, found, _ = text.partition(sentence)
    if not found:
        return None
    end = len(head.rstrip())
    if not end or head[end - 1] not in ".!?" or _PARAGRAPH_BREAK.search(head[end:]):
        return None
    start = max(0, end - _NEIGHBOR_LIMIT)
    boundaries = list(_SENTENCE_BOUNDARY.finditer(head, start, end - 1))
    if start and not boundaries:
        return None
    return head[boundaries[-1].end() if boundaries else 0 : end].strip()


def _phrase(name: str) -> str:
    """Match a lookup label as separate prose words, with an optional plural ending."""
    return r"\s+".join(re.escape(word) for word in name.split("-")) + "s?"


def _same_practitioner(*, actor: str, source: str) -> bool:
    if re.fullmatch(rf"(?:the )?{_phrase(source)}", actor):
        return True
    known = _PRACTITIONER.fullmatch(source.replace("-", " "))
    nearby = _PRACTITIONER.fullmatch(actor.removeprefix("the "))
    return bool(known and nearby and known["topic"] == nearby["topic"])


def _growth_control(*, claim: IdentifiedClaim, nearby: str, cue: str) -> bool:
    source = claim.source or ""
    target = claim.target or ""
    entity = target.removesuffix("-growth")
    if entity == target or not entity or not _CONTROL_GROWTH.search(claim.meaning.casefold()):
        return False
    topic = _phrase(entity)
    if not re.search(rf"\bgrowth of (?:the )?{topic}\b|\b{topic} growth\b", cue):
        return False
    adjustment = _ADJUSTMENT.match(nearby)
    purpose = _DIMENSION_PURPOSE.search(nearby)
    if (
        not adjustment
        or not purpose
        or not _same_practitioner(actor=adjustment["actor"], source=source)
    ):
        return False
    adjusted = nearby[adjustment.end() : purpose.start()].strip()
    return bool(
        re.fullmatch(
            rf"(?:and {_ADJUST} )?(?:the )?{topic}(?:['\u2019]s [\w -]+)?",
            adjusted,
        )
    )


def _signal_transport(*, claim: IdentifiedClaim, nearby: str, evidence: str) -> bool:
    if not claim.source or not claim.target:
        return False
    channel, payload = _phrase(claim.source), _phrase(claim.target)
    passive = re.search(
        rf"\b{payload} (?P<action>{_PASSIVE}) (?:through|via) (?:the )?{channel}\b",
        evidence.casefold(),
    )
    if not passive:
        return False
    action = _TRANSPORT[passive["action"]]
    asserted = re.match(
        rf"^(?:the )?{channel} (?:{action}) (?:the )?{payload}\b", claim.meaning.casefold()
    )
    declared = re.search(
        rf"\b(?:the|a|an) {channel}(?:, [^,;.!?]+? (?:that|which))? {_CHANNEL_ROLE}\b",
        nearby,
    )
    return bool(asserted and declared)


def witness(
    *, claim: IdentifiedClaim, sentence: str, cue: str, source_text: str, evidence: str
) -> str | None:
    """Return an exact independent witness from the preceding sentence of this paragraph."""
    marker = normalized(cue).casefold()
    if not marker.startswith(("by ", "when ")):
        return None
    previous = _previous_sentence(text=source_text, sentence=sentence)
    nearby = normalized(previous or "").casefold()
    if not previous or _QUALIFIED.search(nearby):
        return None
    corroborated = (
        _growth_control(claim=claim, nearby=nearby, cue=marker)
        if marker.startswith("by ")
        else _signal_transport(claim=claim, nearby=nearby, evidence=normalized(evidence))
    )
    return previous if corroborated else None
