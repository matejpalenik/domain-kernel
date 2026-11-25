"""Verify reasoning provenance and required candidate readiness."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, final

import pytest

from domain_kernel import (
    Accept,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    ConceptDefinition,
    DomainModelBundle,
    Iri,
    ModelKind,
    OntologyCapabilities,
    OntologyDocument,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologyLimits,
    OntologySyntax,
    PublicationBlockedError,
    ReasoningModelValidator,
    ReasoningProfile,
    ReasoningRequest,
    ReasoningResult,
    ReasoningSupport,
    ReasoningTask,
    SemanticRegime,
    SemanticStatus,
    load_ontology,
    reason_ontology,
)
from domain_kernel.modeling.application.rdf_projection import RdfLibProjector
from domain_kernel.shared.hashing import hash_bytes
from examples.notebooks.robot_reasoner import ROBOT_ENV, RobotReasoner

if TYPE_CHECKING:
    from domain_kernel import OntologyClosure


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
_IRI = Iri(value="urn:reasoning-test")


def _closure() -> OntologyClosure:
    payload = b"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <urn:reasoning-test> a owl:Ontology .
        <urn:example:Class> a owl:Class .
    """
    return load_ontology(
        document=OntologyDocument(
            pin=OntologyDocumentPin(
                document_iri=_IRI, ontology_iri=_IRI, content_hash=hash_bytes(content=payload)
            ),
            syntax=OntologySyntax.TURTLE,
            payload=payload,
        )
    )


def _request() -> ReasoningRequest:
    return ReasoningRequest(
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        task=ReasoningTask.CONSISTENCY,
    )


@final
class _Adapter:
    def __init__(
        self,
        *,
        consistent: bool | None = True,
        misbound: bool = False,
        wait: bool = False,
        unsatisfiable: bool = False,
    ) -> None:
        self._consistent = consistent
        self._misbound = misbound
        self._wait = wait
        self._unsatisfiable = unsatisfiable
        self.started = asyncio.Event()
        self.finished = asyncio.Event()
        self.capabilities = OntologyCapabilities(
            adapter_id="test/reasoner",
            adapter_version="1",
            reasoning=[
                ReasoningSupport(
                    profile=ReasoningProfile.OWL2_DL,
                    regime=SemanticRegime.OWL_DIRECT,
                    task=task,
                    complete=True,
                )
                for task in (ReasoningTask.CONSISTENCY, ReasoningTask.CLASSIFICATION)
            ],
        )

    async def reason(
        self, *, ontology: OntologyClosure, request: ReasoningRequest, limits: OntologyLimits
    ) -> ReasoningResult:
        if self._wait:
            self.started.set()
            try:
                await asyncio.Future[None]()
            finally:
                self.finished.set()
        return ReasoningResult(
            input_hash=hash_bytes(content=b"wrong") if self._misbound else ontology.content_hash,
            request=request,
            adapter=self.capabilities,
            limits=limits,
            status=SemanticStatus.INCOMPLETE
            if self._consistent is None
            else SemanticStatus.COMPLETE,
            consistent=self._consistent,
            entailed=None,
            unsatisfiable=tuple(
                term
                for parsed in ontology.documents
                for term in parsed.terms
                if self._unsatisfiable and term.entity_kind is OntologyEntityKind.CLASS
            ),
            inferred=(),
            issues=(),
        )


async def test_reasoning_binds_the_attempt_and_rejects_substituted_inputs() -> None:
    closure = _closure()
    request = _request()
    reasoner = _Adapter()
    first = await reason_ontology(ontology=closure, request=request, reasoner=reasoner)
    bounded = await reason_ontology(
        ontology=closure, request=request, reasoner=reasoner, limits=OntologyLimits(timeout_ms=500)
    )
    assert first.status is SemanticStatus.COMPLETE
    assert first.consistent is True
    assert first.entailed is None
    assert first.input_hash == closure.content_hash
    assert bounded.fingerprint != first.fingerprint
    mismatch = await reason_ontology(
        ontology=closure, request=request, reasoner=_Adapter(misbound=True)
    )
    assert mismatch.status is SemanticStatus.FAILED
    assert mismatch.consistent is None
    assert {issue.code for issue in mismatch.issues} == {"reasoning_result_mismatch"}


async def test_limits_and_cancellation_stay_distinct() -> None:
    closure = _closure()
    adapter = _Adapter(wait=True)
    exhausted = await reason_ontology(
        ontology=closure,
        request=_request(),
        reasoner=adapter,
        limits=OntologyLimits(max_statements=1),
    )
    assert exhausted.status is SemanticStatus.INCOMPLETE
    assert exhausted.consistent is None
    assert not adapter.started.is_set()
    expired = await reason_ontology(
        ontology=closure,
        request=_request(),
        reasoner=adapter,
        limits=OntologyLimits(timeout_ms=20),
    )
    assert expired.status is SemanticStatus.TIMEOUT
    assert expired.consistent is None
    assert adapter.finished.is_set()

    cancelled = _Adapter(wait=True)
    task = asyncio.create_task(
        reason_ontology(ontology=closure, request=_request(), reasoner=cancelled)
    )
    _ = await cancelled.started.wait()
    _ = task.cancel()
    with pytest.raises(asyncio.CancelledError):
        _ = await task
    assert cancelled.finished.is_set()


@pytest.mark.parametrize(
    ("consistent", "blocked_code"),
    [(None, "reasoning_incomplete"), (True, "reasoning_unsatisfiable_class"), (True, None)],
)
async def test_required_reasoning_binds_and_controls_publication(
    tmp_path: Path, blocked_code: str | None, *, consistent: bool | None
) -> None:
    classify = blocked_code == "reasoning_unsatisfiable_class"
    validator = ReasoningModelValidator(
        projector=RdfLibProjector(),
        reasoner=_Adapter(consistent=consistent, unsatisfiable=classify),
        request=replace(_request(), task=ReasoningTask.CLASSIFICATION) if classify else _request(),
    )
    client = Client(
        config=ClientConfiguration(base_dir=tmp_path),
        integrations=ClientIntegrations(validators=[validator]),
    )
    project = await client.create_project(actor="editor", name="recruitment")
    model = await project.create_model(
        actor="editor",
        name="formal",
        kind=ModelKind.PROPOSED,
        description="Inspect a formal requirement.",
    )
    case = await model.propose_definition(
        actor="editor",
        name="application-system",
        meaning="A system in the reviewed scope.",
        body=ConceptDefinition(),
        reason="Introduce the formal class.",
    )
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason="Review it."))
    candidate = await model.compile(actor="editor")
    report = await model.validate(actor="editor", candidate=candidate)
    (reasoning,) = report.reasoning
    assert report.candidate_hash == candidate.content_hash
    assert reasoning.consistent is consistent
    if blocked_code is not None:
        with pytest.raises(PublicationBlockedError) as blocked:
            _ = await model.prepare_publication(actor="editor")
        assert blocked_code in {issue.code for issue in blocked.value.issues}
    else:
        assert reasoning.status is SemanticStatus.COMPLETE
        prepared = await model.prepare_publication(actor="editor")
        release = await model.publish(
            actor="publisher", publication=prepared, version="1.0.0", reason="Release the class."
        )
        restored = DomainModelBundle.deserialize(payload=release.serialize())
        assert restored.publication.validation.reasoning == (reasoning,)
        assert restored.publication.candidate.content_hash == candidate.content_hash


async def test_robot_proves_transitive_entailment_with_separate_provenance() -> None:
    jar = os.environ.get(ROBOT_ENV)
    if jar is None:
        pytest.skip("Provision the pinned ROBOT JAR for engine conformance")
    ontology = _formal_closure(
        suffix="source",
        axioms="""
            <urn:class:First> rdfs:subClassOf <urn:class:Middle> .
            <urn:class:Middle> rdfs:subClassOf <urn:class:Last> .
        """,
    )
    query = _formal_closure(
        suffix="query",
        axioms="<urn:class:First> rdfs:subClassOf <urn:class:Last> .",
    )
    engine = RobotReasoner(jar=Path(jar))
    result = await reason_ontology(
        ontology=ontology,
        request=ReasoningRequest(
            profile=ReasoningProfile.OWL2_DL,
            regime=SemanticRegime.OWL_DIRECT,
            task=ReasoningTask.ENTAILMENT,
            query=query,
        ),
        reasoner=engine,
    )
    assert result.status is SemanticStatus.COMPLETE
    assert result.consistent is True
    assert result.entailed is True
    assert len(result.inferred) == 1
    (row,) = result.inferred
    assert row.object == Iri(value="urn:class:Last")
    assert row not in ontology.documents[0].statements
    assert result.input_hash == ontology.content_hash
    assert result.request.query == query


@pytest.mark.parametrize(
    ("axioms", "expected_status", "expected_consistency"),
    [
        ("<urn:class:First> rdfs:label 7 .", SemanticStatus.UNSUPPORTED, None),
        (
            """
            <urn:class:First> rdfs:subClassOf <urn:class:Middle> .
            <urn:class:First> owl:disjointWith <urn:class:Middle> .
            <urn:example:instance> a owl:NamedIndividual, <urn:class:First> .
            """,
            SemanticStatus.COMPLETE,
            False,
        ),
    ],
)
async def test_robot_preserves_unsupported_input_and_inconsistent_entailment(
    axioms: str, expected_status: SemanticStatus, *, expected_consistency: bool | None
) -> None:
    jar = os.environ.get(ROBOT_ENV)
    if jar is None:
        pytest.skip("Provision the pinned ROBOT JAR for engine conformance")
    ontology = _formal_closure(suffix="strict-source", axioms=axioms)
    query = _formal_closure(
        suffix="query", axioms="<urn:class:First> rdfs:subClassOf <urn:class:Last> ."
    )
    result = await reason_ontology(
        ontology=ontology,
        request=ReasoningRequest(
            task=ReasoningTask.ENTAILMENT,
            profile=ReasoningProfile.OWL2_DL,
            regime=SemanticRegime.OWL_DIRECT,
            query=query,
        ),
        reasoner=RobotReasoner(jar=Path(jar)),
    )
    assert result.status is expected_status
    assert result.consistent is expected_consistency
    assert result.entailed is None
    assert result.inferred == ()


def _formal_closure(*, suffix: str, axioms: str) -> OntologyClosure:
    identity = Iri(value=f"urn:reasoning:{suffix}")
    payload = f"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        <{identity.value}> a owl:Ontology .
        <urn:class:First> a owl:Class .
        <urn:class:Middle> a owl:Class .
        <urn:class:Last> a owl:Class .
        {axioms}
    """.encode()
    return load_ontology(
        document=OntologyDocument(
            pin=OntologyDocumentPin(
                document_iri=identity,
                ontology_iri=identity,
                content_hash=hash_bytes(content=payload),
            ),
            syntax=OntologySyntax.TURTLE,
            payload=payload,
        )
    )
