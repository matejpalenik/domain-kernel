"""Evaluate required reasoning on the shared asserted-ontology projection."""

from __future__ import annotations

from asyncio import to_thread
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from domain_kernel._shared.domain.ontology_assets import Iri, OntologyDocumentPin, OntologySyntax
from domain_kernel._shared.domain.ontology_documents import OntologyDocument, OntologyLimits
from domain_kernel._shared.domain.ontology_errors import UnsupportedCapabilityError
from domain_kernel._shared.domain.rdf import OntologyStatement
from domain_kernel._shared.domain.reasoning_capabilities import ReasoningTask, SemanticStatus
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.application.reasoning import reason_ontology
from domain_kernel.modeling.application.validation_ports import SemanticValidator
from domain_kernel.modeling.domain.interchange import RDF_MAPPING, RdfSyntax
from domain_kernel.modeling.domain.rdf_graphs import OWL, RDF, candidate_pin
from domain_kernel.modeling.domain.semantics import ReasoningRequest, reasoning_fingerprint
from domain_kernel.modeling.domain.snapshots import ValidationReport
from domain_kernel.modeling.infrastructure.rdflib_adapter import RdfLibAdapter
from domain_kernel.ontologies import load_ontology
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import DomainKernelError
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.shared.validation import require_exact

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.ontology_closure import OntologyClosure
    from domain_kernel.modeling.application.interchange import SemanticProjector
    from domain_kernel.modeling.application.ontology import OntologyReasoner
    from domain_kernel.modeling.domain.interchange import ValidationGraphs
    from domain_kernel.modeling.domain.semantics import ReasoningResult
    from domain_kernel.modeling.domain.snapshots import Candidate
    from domain_kernel.reference_packs.domain.packs import ReferencePack

_TYPE = Iri(value=f"{RDF}type")
_ONTOLOGY = Iri(value=f"{OWL}Ontology")
_IMPORT = Iri(value=f"{OWL}imports")


def _document(*, identity: Iri, payload: bytes) -> OntologyDocument:
    return OntologyDocument(
        pin=OntologyDocumentPin(
            document_iri=identity, ontology_iri=identity, content_hash=hash_bytes(content=payload)
        ),
        syntax=OntologySyntax.TURTLE,
        payload=payload,
    )


def _header(*, rows: Sequence[OntologyStatement]) -> Iri:
    names = {row.subject for row in rows if row.predicate == _TYPE and row.object == _ONTOLOGY}
    if len(names) == 1 and isinstance(name := next(iter(names)), Iri):
        return name
    raise UnsupportedCapabilityError(message="Supply one named header per asserted ontology.")


def _materialize(*, graphs: ValidationGraphs, limits: OntologyLimits) -> OntologyClosure:
    sources = graphs.asserted_ontologies
    if not sources or any(statement.graph is not None for graph in sources for statement in graph):
        raise UnsupportedCapabilityError(message="Supply the separate asserted ontology graphs.")
    identity = Iri(
        value="urn:domain-kernel:candidate-ontology:"
        + hash_json(
            value=(
                graphs.candidate.content_hash.value,
                graphs.mapping.id.value,
                graphs.mapping.adapter_versions,
            )
        ).value
    )
    names = tuple(_header(rows=rows) for rows in sources)
    imported = {*names, *(closure.root.document_iri for closure in graphs.adopted_ontologies)}
    root_rows = (
        OntologyStatement(subject=identity, predicate=_TYPE, object=_ONTOLOGY),
        *(
            OntologyStatement(subject=identity, predicate=_IMPORT, object=name)
            for name in sorted(imported, key=lambda item: item.value)
        ),
    )
    adapter = RdfLibAdapter()
    root, *payloads = adapter.render(
        statements=(root_rows, *sources), syntax=RdfSyntax.TURTLE, limits=limits
    )
    resources = dict.fromkeys(
        (
            *(
                _document(identity=name, payload=payload)
                for name, payload in zip(names, payloads, strict=True)
            ),
            *(
                parsed.document
                for closure in graphs.adopted_ontologies
                for parsed in closure.documents
            ),
            *(resource for closure in graphs.adopted_ontologies for resource in closure.resources),
        )
    )
    return load_ontology(
        document=_document(identity=identity, payload=root),
        resources=tuple(resources),
        adapter=adapter,
        limits=limits,
    )


@final
class ReasoningModelValidator(SemanticValidator):
    """Require a known consistent asserted ontology and optionally satisfiable named classes."""

    def __init__(
        self,
        *,
        projector: SemanticProjector,
        reasoner: OntologyReasoner,
        request: ReasoningRequest,
        limits: OntologyLimits | None = None,
    ) -> None:
        """Capture the engine and reject requests referring to unpublished class IRIs."""
        require_exact(value=request, expected=ReasoningRequest, field="Reasoning request")
        if request.task is ReasoningTask.ENTAILMENT or request.signature:
            raise ValueError("Require consistency or classification of all named candidate classes")
        self._limits = OntologyLimits() if limits is None else limits
        require_exact(value=self._limits, expected=OntologyLimits, field="Reasoning limits")
        self._projector = projector
        self._reasoner = reasoner
        self._request = request
        self._capabilities = reasoner.capabilities
        self._fingerprint = reasoning_fingerprint(
            request=request,
            adapter=self._capabilities,
            limits=self._limits,
            input_identity=f"candidate/{RDF_MAPPING.value}",
        )

    @property
    @override
    def fingerprint(self) -> str:
        return self._fingerprint

    @override
    async def validate(
        self, *, candidate: Candidate, reference_pack: ReferencePack | None
    ) -> ValidationReport:
        """Bind readiness diagnostics and evidence to the stored candidate."""
        result: ReasoningResult | None = None
        try:
            graphs = await to_thread(
                self._projector.validation_graphs,
                candidate=candidate,
                reference_pack=reference_pack,
                mapping_version=RDF_MAPPING.value,
            )
            if (
                graphs.candidate != candidate_pin(candidate=candidate)
                or graphs.mapping.id != RDF_MAPPING
                or self._reasoner.capabilities != self._capabilities
            ):
                raise UnsupportedCapabilityError
            closure = await to_thread(_materialize, graphs=graphs, limits=self._limits)
            result = await reason_ontology(
                ontology=closure,
                request=self._request,
                reasoner=self._reasoner,
                limits=self._limits,
            )
        except DomainKernelError:
            pass
        issues = self._readiness(result=result)
        return ValidationReport(
            id=ValidationReportId(value=uuid4().hex),
            scope=candidate.scope,
            candidate_id=candidate.id,
            candidate_hash=candidate.content_hash,
            validator_fingerprint=self.fingerprint,
            reference_pack=candidate.reference_pack,
            issues=issues if result is None else (*issues, *result.issues),
            reasoning=() if result is None else (result,),
        )

    @staticmethod
    def _readiness(*, result: ReasoningResult | None) -> tuple[Issue, ...]:
        if result is None or result.status is not SemanticStatus.COMPLETE:
            return (
                Issue(
                    code="reasoning_incomplete",
                    path=("validation", "reasoning"),
                    message="Resolve the unavailable or incomplete required reasoning result.",
                ),
            )
        if result.consistent is not True:
            return (
                Issue(
                    code="reasoning_inconsistent",
                    path=("validation", "reasoning"),
                    message="Review and repair inconsistent asserted ontology axioms.",
                ),
            )
        return tuple(
            Issue(
                code="reasoning_unsatisfiable_class",
                path=("validation", "reasoning", term.term_iri.value),
                message="Review the asserted axioms that make this named class unsatisfiable.",
            )
            for term in result.unsatisfiable
        )
