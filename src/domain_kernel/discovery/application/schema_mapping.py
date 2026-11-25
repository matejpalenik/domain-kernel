"""Shortlist sourced proposals for semantic comparison with the pinned reference pack."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import replace
from itertools import batched
from typing import TYPE_CHECKING

from domain_kernel.discovery.application import schema_evidence as contract
from domain_kernel.discovery.application import schema_model
from domain_kernel.discovery.domain.schema_evidence import SchemaMappingHint
from domain_kernel.reference_packs.domain.contracts import MappingRelation
from domain_kernel.shared.application.inference import InferenceInput
from domain_kernel.shared.contracts import PinnedDefinitionReference
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition
from domain_kernel.shared.errors import InferenceError

if TYPE_CHECKING:
    from domain_kernel.discovery.application.ports import SchemaStageCall
    from domain_kernel.discovery.domain.models import DiscoveryDraft, ExtractionIntent
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.reference_packs.domain.contracts import ReferenceDefinition
    from domain_kernel.shared.contracts import DefinitionReference
    from domain_kernel.shared.domain.entities.definition import Definition

_WORD: re.Pattern[str] = re.compile(r"[^\W_]+")
_COMMON = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "to",
        "is",
        "in",
        "for",
        "by",
        "of",
        "that",
        "with",
        "its",
        "as",
        "are",
        "can",
        "be",
        "from",
    ]
)
_LIMIT = 5


def _words(*, text: str) -> set[str]:
    return set(_WORD.findall(text.casefold())) - _COMMON


def _text(*, item: Definition | ReferenceDefinition) -> str:
    return " ".join(
        (item.name, item.meaning, *(label.text.value for label in item.terminology.labels))
    )


def _shortlist(
    *, locals_: tuple[Definition, ...], members: tuple[ReferenceDefinition, ...]
) -> list[tuple[Definition, ReferenceDefinition]]:
    by_kind: defaultdict[str, list[int]] = defaultdict(list)
    inverted: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    for i, member in enumerate(members):
        kind = member.body.kind.value
        by_kind[kind].append(i)
        for token in _words(text=_text(item=member)):
            inverted[kind, token].append(i)
    result: list[tuple[Definition, ReferenceDefinition]] = []
    for item in locals_:
        kind = item.kind.value
        scores: defaultdict[int, float] = defaultdict(float)
        for token in _words(text=_text(item=item)):
            matches = inverted.get((kind, token), ())
            for i in matches:
                scores[i] += 1 / len(matches)
        ranked = sorted(scores, key=lambda i: (-scores[i], members[i].name, members[i].id.value))
        candidates = tuple(dict.fromkeys((*ranked, *by_kind[kind][:_LIMIT])))
        result.extend((item, members[i]) for i in candidates[:_LIMIT])
    return result


def _members(*, pack: ReferencePack) -> tuple[ReferenceDefinition, ...]:
    return tuple(
        {
            item.id: item
            for item in (
                *pack.definitions,
                *(item for pattern in pack.patterns for item in pattern.definitions),
            )
        }.values()
    )


async def compare(
    *,
    draft: DiscoveryDraft,
    pack: ReferencePack,
    intent: ExtractionIntent,
    call: SchemaStageCall,
    retry_cycle: int | None,
) -> DiscoveryDraft:
    """Save suggestions without promoting their relation to a reviewed decision."""
    locals_ = tuple(item.definition for item in draft.proposals)
    members = _members(pack=pack)
    local_names = {
        item.id.value: _text(item=item) for item in (*draft.context.approved_definitions, *locals_)
    }
    reference_names = {item.id.value: _text(item=item) for item in members}
    evidence_text = {
        w.evidence: w.quote for row in draft.schema_observations for w in row.witnesses
    }
    suggestions: list[SchemaMappingHint] = []
    responses_in = responses_out = 0
    for group in batched(_shortlist(locals_=locals_, members=members), 12, strict=False):
        local_evidence = tuple(dict.fromkeys(e for item, _ in group for e in item.evidence))
        inputs = tuple(InferenceInput(text=evidence_text[e], evidence=(e,)) for e in local_evidence)
        pairs = [
            {
                "pair": i,
                "kind": item.kind.value,
                "local": _text(item=item),
                "reference": _text(item=target),
                "local_direction": (
                    [
                        local_names.get(_identifier(value=item.body.source_concept_id)),
                        local_names.get(_identifier(value=item.body.target_concept_id)),
                    ]
                    if isinstance(item.body, RelationshipDefinition)
                    else None
                ),
                "reference_direction": (
                    [
                        reference_names.get(_identifier(value=target.body.source_concept_id)),
                        reference_names.get(_identifier(value=target.body.target_concept_id)),
                    ]
                    if isinstance(target.body, RelationshipDefinition)
                    else None
                ),
            }
            for i, (item, target) in enumerate(group, 1)
        ]
        frame: dict[str, object] = {"scope": draft.context.model_description, "pairs": pairs}
        if retry_cycle is not None:
            frame["mapping_retry_cycle"] = retry_cycle
        response = await call(
            intent=intent,
            stage=contract.MAPPING_STAGE,
            instructions=contract.MAPPING,
            schema=schema_model.response_schema(contract.Mappings),
            inputs=inputs,
            context_json=json.dumps(frame),
        )
        responses_in += response.input_tokens or 0
        responses_out += response.output_tokens or 0
        reviewed = schema_model.parse(model=contract.Mappings, payload=response.output_json)
        seen: set[int] = set()
        for hint in reviewed.suggestions:
            if hint.pair in seen or hint.pair > len(group) or not hint.reason.strip():
                raise InferenceError(message="Compare only unique, shortlisted reference pairs.")
            seen.add(hint.pair)
            item, target = group[hint.pair - 1]
            suggestions.append(
                SchemaMappingHint(
                    definition=item.id,
                    reference=target.id,
                    relation=MappingRelation(hint.relation),
                    reason=hint.reason,
                )
            )
    return replace(
        draft,
        schema_mappings=tuple(suggestions),
        provenance=replace(
            draft.provenance,
            input_tokens=(draft.provenance.input_tokens or 0) + responses_in,
            output_tokens=(draft.provenance.output_tokens or 0) + responses_out,
        ),
    )


def _identifier(*, value: DefinitionReference) -> str:
    return (
        value.definition_id.value if isinstance(value, PinnedDefinitionReference) else value.value
    )
