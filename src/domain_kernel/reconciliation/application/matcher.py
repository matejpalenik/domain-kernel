"""Select lexical candidates and retain exact inputs for human review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from domain_kernel.reference_packs.domain.contracts import ReferenceDefinition

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel.reconciliation.application.ports import SimilarityScorer
    from domain_kernel.reference_packs.api.packs import ReferencePack


_WORD = re.compile(r"[^\W_]+")
_MINIMUM_FUZZY_SCORE = 0.80
_MAX_CANDIDATES = 5


@dataclass(frozen=True, kw_only=True)
class Candidate[T]:
    """A target to inspect with its lexical reason for appearing."""

    target: T
    reason: str


def _labels(*, item: Definition | ReferenceDefinition) -> tuple[str, ...]:
    terms = tuple(label.text.value for label in item.terminology.labels)
    names = (item.name, *terms)
    if not isinstance(item, ReferenceDefinition):
        names = (*names, item.display_name, *item.aliases)
    normalized = tuple(" ".join(_WORD.findall(name.casefold())) for name in names)
    return tuple(dict.fromkeys(name for name in normalized if name))


def reference_members(*, pack: ReferencePack) -> tuple[ReferenceDefinition, ...]:
    """Walk the pack and its patterns once per exact member identity."""
    return tuple(
        {
            item.id: item
            for item in (
                *pack.definitions,
                *(item for pattern in pack.patterns for item in pattern.definitions),
            )
        }.values()
    )


@final
class EvidenceBasedConceptMatcher:
    """Apply lexical matching within each layer and definition kind."""

    def __init__(self, *, similarity: SimilarityScorer | None = None) -> None:
        """Bind the optional scorer selected by the caller."""
        self._similarity = similarity

    def _signal(self, *, left: tuple[str, ...], right: tuple[str, ...]) -> tuple[float, str] | None:
        if set(left).intersection(right):
            return 2.0, "Names, labels or aliases coincide. Compare the cited meanings."
        if any(f" {a} " in f" {b} " or f" {b} " in f" {a} " for a in left for b in right):
            return 1.0, "Names share a complete phrase. Inspect the scope of each meaning."
        if self._similarity is None:
            return None
        score = max(
            (self._similarity.score(left=a, right=b) for a in left for b in right),
            default=0.0,
        )
        if type(score) is not float or not 0 <= score <= 1:
            raise ValueError("Use a lexical similarity score between zero and one.")
        if score >= _MINIMUM_FUZZY_SCORE:
            return score, "The configured scorer found similar labels. Review the exact meanings."
        return None

    def _candidates[T: (Definition, ReferenceDefinition)](
        self, *, local: Definition, targets: Sequence[T]
    ) -> tuple[Candidate[T], ...]:
        left = _labels(item=local)
        ranked: list[tuple[float, Candidate[T]]] = []
        for target in targets:
            if local.body.kind is target.body.kind:
                signal = self._signal(left=left, right=_labels(item=target))
                if signal is not None:
                    score, reason = signal
                    ranked.append((score, Candidate(target=target, reason=reason)))
        ranked.sort(key=lambda row: (-row[0], row[1].target.name, row[1].target.id.value))
        return tuple(item for _, item in ranked[:_MAX_CANDIDATES])

    def source(
        self, *, proposed: Definition, active: Sequence[Definition]
    ) -> tuple[Candidate[Definition], ...]:
        """Find reviewed local targets for a source occurrence."""
        return self._candidates(local=proposed, targets=active)

    def reference(
        self, *, local: Definition, members: Sequence[ReferenceDefinition]
    ) -> tuple[Candidate[ReferenceDefinition], ...]:
        """Find reference targets for an active local definition."""
        return self._candidates(local=local, targets=members)
