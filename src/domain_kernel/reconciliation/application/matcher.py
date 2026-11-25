"""Select lexical candidates and retain exact inputs for human review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.contracts import ReferenceDefinition
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel.reconciliation.application.ontology_shortlist import OntologyShortlist
    from domain_kernel.reconciliation.application.ports import SimilarityScorer
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.contracts import DefinitionReference
    from domain_kernel.shared.domain.entities.definition import Definition


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


def _compatible_reference_slot(
    *,
    local: DefinitionReference,
    target: DefinitionReference,
    alignments: Mapping[DefinitionId, ReferenceDefinitionId],
) -> bool:
    if isinstance(local, DefinitionId) and isinstance(target, ReferenceDefinitionId):
        mapped = alignments.get(local)
        return mapped is None or mapped == target
    return True


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
        self,
        *,
        local: Definition,
        members: Sequence[ReferenceDefinition],
        endpoint_alignments: Mapping[DefinitionId, ReferenceDefinitionId] | None = None,
        ontology: OntologyShortlist | None = None,
    ) -> tuple[Candidate[ReferenceDefinition], ...]:
        """Rank reference targets after applying known reviewed endpoint directions."""
        if ontology is not None and isinstance(local.body, RelationshipDefinition):
            return self._ontology_reference(
                local=local,
                body=local.body,
                members=members,
                endpoint_alignments=endpoint_alignments or {},
                ontology=ontology,
            )
        if isinstance(local.body, RelationshipDefinition) and endpoint_alignments:
            members = tuple(
                member
                for member in members
                if isinstance(member.body, RelationshipDefinition)
                and _compatible_reference_slot(
                    local=local.body.source_concept_id,
                    target=member.body.source_concept_id,
                    alignments=endpoint_alignments,
                )
                and _compatible_reference_slot(
                    local=local.body.target_concept_id,
                    target=member.body.target_concept_id,
                    alignments=endpoint_alignments,
                )
            )
        return self._candidates(local=local, targets=members)

    def _ontology_reference(
        self,
        *,
        local: Definition,
        body: RelationshipDefinition,
        members: Sequence[ReferenceDefinition],
        endpoint_alignments: Mapping[DefinitionId, ReferenceDefinitionId],
        ontology: OntologyShortlist,
    ) -> tuple[Candidate[ReferenceDefinition], ...]:
        labels = _labels(item=local)
        ranked: list[tuple[int, float, Candidate[ReferenceDefinition]]] = []
        for target in members:
            direction = ontology.direction(
                local=body, reference=target, alignments=endpoint_alignments
            )
            if direction is None:
                continue
            compatible_roles, inverse_labels = direction
            signal = self._signal(left=labels, right=_labels(item=target))
            if signal is None and set(labels).intersection(inverse_labels):
                signal = (
                    2.0,
                    "A declared inverse matches the label in the local direction.",
                )
            if signal is not None:
                score, reason = signal
                if compatible_roles:
                    reason += " Reviewed endpoints or pinned supertypes support this direction."
                ranked.append((compatible_roles, score, Candidate(target=target, reason=reason)))
        ranked.sort(key=lambda row: (-row[0], -row[1], row[2].target.name, row[2].target.id.value))
        return tuple(item for _, _, item in ranked[:_MAX_CANDIDATES])
