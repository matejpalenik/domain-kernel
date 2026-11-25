"""Immutable questions and evidence for explicit formal reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.module_capabilities import (
    ModuleExtractionMethod,
    ModuleExtractionSupport,
    ModuleGuarantee,
)
from domain_kernel.shared.domain.ontology_assets import (
    Iri,
    OntologyEntityKind,
    OntologyTermReference,
)
from domain_kernel.shared.domain.ontology_closure import OntologyClosure, pin_key
from domain_kernel.shared.domain.ontology_documents import OntologyCapabilities, OntologyLimits
from domain_kernel.shared.domain.rdf import OntologyStatement
from domain_kernel.shared.domain.reasoning_capabilities import (
    ReasoningProfile,
    ReasoningTask,
    SemanticRegime,
    SemanticStatus,
)
from domain_kernel.shared.hashing import JsonValue, hash_json
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


def _engine_identity(*, adapter: OntologyCapabilities) -> dict[str, JsonValue]:
    identity: dict[str, JsonValue] = {
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
    }
    if adapter.extraction:
        identity["extraction"] = [
            (item.method.value, item.profile.value, item.regime.value, item.guarantee.value)
            for item in adapter.extraction
        ]
    return identity


def _term_identity(*, term: OntologyTermReference) -> tuple[str, ...]:
    return (*pin_key(pin=term.source), term.term_iri.value, term.entity_kind.value)


def _limit_identity(*, limits: OntologyLimits) -> tuple[int, ...]:
    return (limits.max_bytes, limits.max_documents, limits.max_statements, limits.timeout_ms)


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
            "signature": [_term_identity(term=term) for term in request.signature],
            **_engine_identity(adapter=adapter),
            "limits": _limit_identity(limits=limits),
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


@dataclass(frozen=True, kw_only=True)
class OntologyModuleResult:
    """Evidence for one exact extraction, with a usable closure only on success."""

    source_hash: ContentHash
    ontology_iri: Iri
    limits: OntologyLimits
    seeds: Sequence[OntologyTermReference]
    method: ModuleExtractionMethod
    profile: ReasoningProfile
    regime: SemanticRegime
    adapter: OntologyCapabilities
    status: SemanticStatus
    guarantee: ModuleGuarantee
    signature: Sequence[OntologyTermReference]
    ontology: OntologyClosure | None
    issues: Sequence[Issue]
    fingerprint: str = ""

    def __post_init__(self) -> None:
        """Capture the exact options and restrict usable modules to complete results."""
        require_exact(value=self.source_hash, expected=ContentHash, field="Module source")
        require_exact(value=self.ontology_iri, expected=Iri, field="Derived ontology IRI")
        require_exact(value=self.limits, expected=OntologyLimits, field="Module limits")
        require_exact(value=self.adapter, expected=OntologyCapabilities, field="Module adapter")
        require_exact(value=self.status, expected=SemanticStatus, field="Module status")
        _ = ModuleExtractionSupport(
            method=self.method, profile=self.profile, regime=self.regime, guarantee=self.guarantee
        )
        for name, values in (("seeds", self.seeds), ("signature", self.signature)):
            terms = snapshot_sequence(items=values, item_type=OntologyTermReference, field=name)
            if len(set(terms)) != len(terms):
                raise ValueError("Select each exact term once in the module seed and signature")
            object.__setattr__(self, name, terms)
        if not self.seeds:
            raise ValueError("Select the exact source terms that seed extraction")
        object.__setattr__(
            self,
            "issues",
            snapshot_sequence(items=self.issues, item_type=Issue, field="Module issues"),
        )
        self._require_usable_outcome()
        self._seal_provenance()

    def _require_usable_outcome(self) -> None:
        if self.status is SemanticStatus.COMPLETE:
            require_exact(value=self.ontology, expected=OntologyClosure, field="Completed module")
            if self.ontology is not None and self.ontology.root.ontology_iri != self.ontology_iri:
                raise ValueError("Use the exact requested identity for the derived ontology")
            if not set(self.seeds) <= set(self.signature):
                raise ValueError("Preserve the selected source terms in the module signature")
        elif (
            self.ontology is not None
            or self.signature
            or self.guarantee is not ModuleGuarantee.NONE
        ):
            raise ValueError("A usable module and a guarantee require complete extraction")

    def _seal_provenance(self) -> None:
        expected = hash_json(
            value={
                "source": self.source_hash.value,
                "derived": self.ontology_iri.value,
                "method": self.method.value,
                "profile": self.profile.value,
                "regime": self.regime.value,
                "seeds": [_term_identity(term=term) for term in self.seeds],
                **_engine_identity(adapter=self.adapter),
                "limits": _limit_identity(limits=self.limits),
            }
        ).value
        require_exact(value=self.fingerprint, expected=str, field="Module fingerprint")
        if self.fingerprint and self.fingerprint != expected:
            raise ValueError("Match the exact extraction request and engine fingerprint")
        object.__setattr__(self, "fingerprint", expected)
