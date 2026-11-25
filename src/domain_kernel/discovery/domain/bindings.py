"""Durable evidence for the directed participants in a discovery claim."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.domain.value_objects.relation_type_ref import RelationTypeRef
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class EndpointBinding:
    """One source occurrence and its chosen concept, when resolved."""

    mention_id: str
    evidence: Evidence
    start: int
    end: int
    quote: str
    definition_id: DefinitionId | None
    definition_revision: int | None

    def __post_init__(self) -> None:
        """Keep the exact character span and definition pin together."""
        TextValidation.require_text(value=self.mention_id, field="Endpoint mention")
        TextValidation.require_text(value=self.quote, field="Endpoint quotation")
        RuntimeTypeValidation.require_exact(
            value=self.evidence, expected=Evidence, field="Endpoint evidence"
        )
        RuntimeTypeValidation.require_exact(value=self.start, expected=int, field="Endpoint start")
        RuntimeTypeValidation.require_exact(value=self.end, expected=int, field="Endpoint end")
        if self.start < 0 or self.end - self.start != len(self.quote):
            raise ValueError("Use the exact nonempty endpoint span.")
        if self.definition_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.definition_id, expected=DefinitionId, field="Endpoint concept"
            )
            if type(self.definition_revision) is not int or self.definition_revision < 1:
                raise ValueError("Pin the endpoint definition revision.")
        elif self.definition_revision is not None:
            raise ValueError("Supply the endpoint definition with its revision.")


@dataclass(frozen=True, kw_only=True)
class BindingWitness:
    """The issued citation and quotation that support an action or identity decision."""

    evidence: Evidence
    quote: str

    def __post_init__(self) -> None:
        """Require a nonblank quotation from a recorded source."""
        RuntimeTypeValidation.require_exact(
            value=self.evidence, expected=Evidence, field="Binding evidence"
        )
        TextValidation.require_text(value=self.quote, field="Binding quotation")


@dataclass(frozen=True, kw_only=True)
class HeldRelationship:
    """A verified source claim whose directed participants still need review."""

    claim_id: str
    predicate: str
    source: str
    target: str
    meaning: str
    reason: str
    evidence: Sequence[BindingWitness]
    conditions: Sequence[str] = ()
    exceptions: Sequence[str] = ()
    dependency_ids: Sequence[DefinitionId] = ()
    relation_type: RelationTypeRef | None = None

    def __post_init__(self) -> None:
        """Retain the original ordered assertion and its issued citations."""
        for value in (
            self.claim_id,
            self.predicate,
            self.source,
            self.target,
            self.meaning,
            self.reason,
        ):
            TextValidation.require_text(value=value, field="Held relationship")
        if self.relation_type is not None:
            RuntimeTypeValidation.require_exact(
                value=self.relation_type, expected=RelationTypeRef, field="Relation type"
            )
        evidence = SequenceValidation.snapshot_sequence(
            items=self.evidence, item_type=BindingWitness, field="Held evidence"
        )
        if not evidence:
            raise ValueError("Supply evidence for the held relationship.")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(
            self,
            "dependency_ids",
            SequenceValidation.snapshot_sequence(
                items=self.dependency_ids,
                item_type=DefinitionId,
                field="Held concept dependencies",
            ),
        )
        for name in ("conditions", "exceptions"):
            values = self.conditions if name == "conditions" else self.exceptions
            object.__setattr__(
                self,
                name,
                SequenceValidation.snapshot_sequence(items=values, item_type=str, field=name),
            )


@dataclass(frozen=True, kw_only=True)
class RelationshipBinding:
    """A directed claim with its evidence, resolved proposal, or review reason."""

    claim_id: str
    relationship_id: DefinitionId | None
    source: EndpointBinding | None
    target: EndpointBinding | None
    evidence: Sequence[BindingWitness] = ()
    identity_evidence: Sequence[BindingWitness] = ()
    origin_claim_ids: Sequence[str] = ()
    reason: str | None = None
    previous_source: EndpointBinding | None = None
    previous_target: EndpointBinding | None = None

    def __post_init__(self) -> None:
        """Require exact participants for any emitted relationship definition."""
        TextValidation.require_text(value=self.claim_id, field="Relationship claim")
        for endpoint in (self.source, self.target, self.previous_source, self.previous_target):
            if endpoint is not None:
                RuntimeTypeValidation.require_exact(
                    value=endpoint, expected=EndpointBinding, field="Endpoint binding"
                )
        if self.relationship_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.relationship_id, expected=DefinitionId, field="Relationship"
            )
            if any(e is None or e.definition_id is None for e in (self.source, self.target)):
                raise ValueError("Bind both endpoints of the relationship.")
            if self.reason is not None or not self.evidence:
                raise ValueError("Supply verified evidence for the emitted relationship.")
        elif self.reason is None:
            raise ValueError("Explain why the relationship was held.")
        else:
            TextValidation.require_text(value=self.reason, field="Held relationship reason")
        for name in ("evidence", "identity_evidence"):
            value = self.evidence if name == "evidence" else self.identity_evidence
            object.__setattr__(
                self,
                name,
                SequenceValidation.snapshot_sequence(
                    items=value, item_type=BindingWitness, field=name
                ),
            )
        object.__setattr__(
            self,
            "origin_claim_ids",
            SequenceValidation.snapshot_sequence(
                items=self.origin_claim_ids, item_type=str, field="Claim origins"
            ),
        )
