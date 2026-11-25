"""Select deferred evidence and prevent a continuation from reproposing delivered claims."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from domain_kernel.discovery.domain.coverage import DiscoveryCoverage
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition
from domain_kernel.shared.errors import InferenceError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel.discovery.domain.bindings import HeldRelationship
    from domain_kernel.discovery.domain.models import (
        DiscoveryDraft,
        InterpretationContext,
        Proposal,
    )
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.shared.application.inference import InferenceInput
    from domain_kernel.shared.contracts import DefinitionReference
    from domain_kernel.shared.domain.entities.definition import Definition


def select_windows(
    *, previous: DiscoveryDraft, inputs: Sequence[InferenceInput]
) -> tuple[tuple[int, int, int], ...]:
    """Map durable parent spans onto identical captured inputs."""
    positions = {part.evidence[0]: index for index, part in enumerate(inputs, 1)}
    result: list[tuple[int, int, int]] = []
    for manifest in previous.coverage:
        for window in manifest.deferred:
            citation = positions.get(window.evidence)
            if citation is None or window.end > len(inputs[citation - 1].text):
                raise InferenceError(message="Reopen the exact deferred source window.")
            result.append((citation, window.start, window.end))
    if not result and not any(item.has_deferred for item in previous.coverage):
        raise InferenceError(message="Select a run with deferred omission windows.")
    return tuple(result)


def pending_concepts(
    *, ancestry: Sequence[DiscoveryDraft], context: InterpretationContext
) -> tuple[tuple[str, str, str], ...]:
    """Make older proposed endpoints visible only as review dependencies."""
    approved = {
        item.name for item in context.approved_definitions if item.kind is DefinitionKind.CONCEPT
    }
    pending: dict[str, tuple[str, str, str]] = {}
    for draft in ancestry:
        for p in draft.proposals:
            item = p.definition
            if item.kind is DefinitionKind.CONCEPT and item.name not in approved:
                _ = pending.setdefault(item.name, (item.name, item.id.value, item.meaning))
    return tuple(pending.values())


def merge_coverage(
    *, completed: tuple[DiscoveryCoverage, ...], previous: DiscoveryDraft
) -> tuple[DiscoveryCoverage, ...]:
    """Carry earlier completed windows forward without reprocessing them."""
    inherited = {manifest.source: manifest.completed for manifest in previous.coverage}
    return tuple(
        DiscoveryCoverage(
            source=manifest.source,
            windows=tuple(
                sorted(
                    (*inherited.get(manifest.source, ()), *manifest.windows),
                    key=lambda item: (item.evidence.id.value, item.start),
                )
            ),
        )
        for manifest in completed
    )


def _meaning(item: Definition, *, names: Mapping[DefinitionReference, str]) -> tuple[str, ...]:
    body = item.body
    key = (item.kind.value, " ".join(item.display_name.split()), " ".join(item.meaning.split()))
    if isinstance(body, RelationshipDefinition):
        return (
            *key,
            names.get(body.source_concept_id, str(body.source_concept_id)),
            names.get(body.target_concept_id, str(body.target_concept_id)),
            *(
                (body.relation_type.vocabulary, body.relation_type.version, body.relation_type.code)
                if body.relation_type is not None
                else ()
            ),
        )
    return key


def delta(
    *,
    proposals: tuple[Proposal, ...],
    ancestry: Sequence[DiscoveryDraft],
    context: InterpretationContext,
    provisional_holds: Mapping[DefinitionId, HeldRelationship],
) -> tuple[tuple[Proposal, ...], tuple[HeldRelationship, ...]]:
    """Deduplicate the draft, then resolve provisional holds by retained concept ID."""
    prior = [p.definition for draft in ancestry for p in draft.proposals]
    definitions = [*context.approved_definitions, *prior, *(p.definition for p in proposals)]
    names: dict[DefinitionReference, str] = {item.id: item.name for item in definitions}
    old = {_meaning(item, names=names) for item in prior}
    approved = {
        item.name: item.id
        for item in context.approved_definitions
        if item.kind is DefinitionKind.CONCEPT
    }
    reused: dict[DefinitionReference, DefinitionReference] = {
        p.definition.id: approved[p.definition.name]
        for p in proposals
        if p.definition.kind is DefinitionKind.CONCEPT
        and p.definition.name in approved
        and _meaning(p.definition, names=names) in old
    }
    retained = [p for p in proposals if _meaning(p.definition, names=names) not in old]
    surviving = set(approved.values()) | {
        p.definition.id for p in retained if p.definition.kind is DefinitionKind.CONCEPT
    }
    previous_concepts: dict[tuple[str, ...], DefinitionId] = {}
    for item in prior:
        if item.kind is DefinitionKind.CONCEPT:
            _ = previous_concepts.setdefault((item.name, *_meaning(item, names=names)), item.id)
    duplicates = {
        p.definition.id: previous_concepts[(p.definition.name, *key)]
        for p in proposals
        if p.definition.kind is DefinitionKind.CONCEPT
        and (key := _meaning(p.definition, names=names)) in old
        and (p.definition.name, *key) in previous_concepts
    }
    result: list[Proposal] = []
    held: list[HeldRelationship] = []
    for proposal in retained:
        item = proposal.definition
        included = proposal
        if isinstance(body := item.body, RelationshipDefinition):
            bound = replace(
                body,
                source_concept_id=reused.get(body.source_concept_id, body.source_concept_id),
                target_concept_id=reused.get(body.target_concept_id, body.target_concept_id),
            )
            missing = [
                endpoint
                for endpoint in (bound.source_concept_id, bound.target_concept_id)
                if endpoint not in surviving
            ]
            if missing and (hold := provisional_holds.get(item.id)) is not None:
                dependencies = tuple(
                    dict.fromkeys(duplicates[e] for e in missing if e in duplicates)
                )
                held.append(
                    replace(
                        hold,
                        dependency_ids=dependencies,
                        relation_type=bound.relation_type,
                        reason=hold.reason
                        if dependencies
                        else "Review the endpoint proposal removed by deduplication.",
                    )
                )
                continue
            included = replace(proposal, definition=replace(item, body=bound))
        result.append(included)
    return tuple(result), tuple(held)
