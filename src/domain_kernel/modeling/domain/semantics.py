"""Immutable questions and evidence for explicit formal reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.ontology_assets import OntologyEntityKind, OntologyTermReference
from domain_kernel._shared.domain.ontology_closure import OntologyClosure, pin_key
from domain_kernel._shared.domain.ontology_documents import OntologyCapabilities, OntologyLimits
from domain_kernel._shared.domain.rdf import OntologyStatement
from domain_kernel._shared.domain.reasoning_capabilities import (
    ReasoningProfile,
    ReasoningTask,
    SemanticRegime,
    SemanticStatus,
)
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class ReasoningRequest:
    """A question about one exact ontology under explicit semantics."""

    profile: ReasoningProfile
    regime: SemanticRegime
    task: ReasoningTask
    signature: Sequence[OntologyTermReference] = ()
    query: OntologyClosure | None = None

    def __post_init__(self) -> None:
        """Require a complete query or a scope of exact named classes when applicable."""
        require_exact(value=self.profile, expected=ReasoningProfile, field="Reasoning profile")
        require_exact(value=self.regime, expected=SemanticRegime, field="Semantic regime")
        require_exact(value=self.task, expected=ReasoningTask, field="Reasoning task")
        signature = snapshot_sequence(
            items=self.signature, item_type=OntologyTermReference, field="Classification classes"
        )
        if signature and (
            self.task is not ReasoningTask.CLASSIFICATION
            or len(set(signature)) != len(signature)
            or any(term.entity_kind is not OntologyEntityKind.CLASS for term in signature)
        ):
            raise ValueError("Select distinct named classes only for classification")
        object.__setattr__(self, "signature", signature)
        if self.task is ReasoningTask.ENTAILMENT:
            require_exact(value=self.query, expected=OntologyClosure, field="Entailment query")
        elif self.query is not None:
            raise ValueError("Supply a query only for entailment")


def reasoning_fingerprint(
    *,
    request: ReasoningRequest,
    adapter: OntologyCapabilities,
    limits: OntologyLimits,
    input_identity: str,
) -> str:
    """Seal the exact question, engine capabilities, bounds and input identity."""
    return hash_json(
        value={
            "input": input_identity,
            "profile": request.profile.value,
            "regime": request.regime.value,
            "task": request.task.value,
            "query": None if request.query is None else request.query.content_hash.value,
            "signature": [
                (*pin_key(pin=term.source), term.term_iri.value, term.entity_kind.value)
                for term in request.signature
            ],
            "adapter": (adapter.adapter_id, adapter.adapter_version),
            "parse": [syntax.value for syntax in adapter.parse_syntaxes],
            "serialize": [syntax.value for syntax in adapter.serialize_syntaxes],
            "datatypes": [iri.value for iri in adapter.datatypes],
            "features": adapter.feature_ids,
            "reasoning": [
                (
                    item.profile.value,
                    item.regime.value,
                    item.task.value,
                    item.complete,
                    item.restrictions,
                )
                for item in adapter.reasoning
            ],
            "limits": (
                limits.max_bytes,
                limits.max_documents,
                limits.max_statements,
                limits.timeout_ms,
            ),
        }
    ).value


@dataclass(frozen=True, kw_only=True)
class ReasoningResult:
    """Adapter outcome with separate inferred statements and exact provenance."""

    input_hash: ContentHash
    request: ReasoningRequest
    adapter: OntologyCapabilities
    limits: OntologyLimits
    status: SemanticStatus
    consistent: bool | None
    entailed: bool | None
    unsatisfiable: Sequence[OntologyTermReference]
    inferred: Sequence[OntologyStatement]
    issues: Sequence[Issue]
    explanations: Sequence[str] = ()
    fingerprint: str = ""

    def __post_init__(self) -> None:
        """Require truthful result combinations and seal the attempt provenance."""
        require_exact(value=self.input_hash, expected=ContentHash, field="Reasoning input")
        require_exact(value=self.request, expected=ReasoningRequest, field="Reasoning request")
        require_exact(value=self.adapter, expected=OntologyCapabilities, field="Reasoner")
        require_exact(value=self.limits, expected=OntologyLimits, field="Reasoning limits")
        require_exact(value=self.status, expected=SemanticStatus, field="Reasoning status")
        for name, value in (("Consistency", self.consistent), ("Entailment", self.entailed)):
            if value is not None:
                require_exact(value=value, expected=bool, field=name)
        for name, values, item_type in (
            ("unsatisfiable", self.unsatisfiable, OntologyTermReference),
            ("inferred", self.inferred, OntologyStatement),
            ("issues", self.issues, Issue),
            ("explanations", self.explanations, str),
        ):
            object.__setattr__(
                self, name, snapshot_sequence(items=values, item_type=item_type, field=name)
            )
        for explanation in self.explanations:
            require_text(value=explanation, field="Reasoning explanation")
        self._require_valid_outcome()
        expected = reasoning_fingerprint(
            request=self.request,
            adapter=self.adapter,
            limits=self.limits,
            input_identity=self.input_hash.value,
        )
        require_exact(value=self.fingerprint, expected=str, field="Reasoning fingerprint")
        if self.fingerprint and self.fingerprint != expected:
            raise ValueError("Match the exact reasoning input and engine fingerprint")
        object.__setattr__(self, "fingerprint", expected)

    def _require_valid_outcome(self) -> None:
        if self.status in (
            SemanticStatus.UNSUPPORTED,
            SemanticStatus.TIMEOUT,
            SemanticStatus.FAILED,
        ) and (self.consistent is not None or self.entailed is not None):
            raise ValueError("Leave unestablished consistency and entailment unknown")
        if self.status is SemanticStatus.COMPLETE and self.consistent is None:
            raise ValueError("A complete result requires known consistency")
        if self.consistent is not True and (
            self.entailed is not None or self.inferred or self.unsatisfiable
        ):
            raise ValueError("A reasoning conclusion requires known consistent input")
        if self.request.task is not ReasoningTask.ENTAILMENT and self.entailed is not None:
            raise ValueError("Report entailment only for a requested query")
        if (
            self.status is SemanticStatus.COMPLETE
            and self.consistent is True
            and self.request.task is ReasoningTask.ENTAILMENT
            and self.entailed is None
        ):
            raise ValueError("A complete entailment result requires a known answer")
        if self.unsatisfiable and (
            self.request.task is not ReasoningTask.CLASSIFICATION
            or len(set(self.unsatisfiable)) != len(self.unsatisfiable)
            or any(term.entity_kind is not OntologyEntityKind.CLASS for term in self.unsatisfiable)
        ):
            raise ValueError("Report distinct named unsatisfiable classes for classification")
