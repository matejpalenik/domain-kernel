"""Verify exact locality extraction and retained semantic evidence."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, final

import pytest

from domain_kernel import (
    Iri,
    ModuleExtractionMethod,
    ModuleExtractionSupport,
    ModuleGuarantee,
    OntologyCapabilities,
    OntologyDocument,
    OntologyDocumentPin,
    OntologyLimits,
    OntologyModuleResult,
    OntologySyntax,
    ReasoningProfile,
    ReasoningRequest,
    ReasoningTask,
    SemanticRegime,
    SemanticStatus,
    extract_ontology_module,
    load_ontology,
    reason_ontology,
)
from domain_kernel.shared.hashing import hash_bytes
from examples.notebooks.robot_reasoner import ROBOT_ENV, RobotReasoner, named_class_scope

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel import OntologyClosure, OntologyTermReference

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
_FIRST = Iri(value="urn:module:First")
_MIDDLE = Iri(value="urn:module:Middle")
_LAST = Iri(value="urn:module:Last")
_FOREIGN = Iri(value="urn:module:Unrelated")
_ROOT = Iri(value="urn:module:source")
_DERIVED = Iri(value="urn:module:derived")


def _source() -> OntologyClosure:
    return named_class_scope(
        identity=_ROOT,
        specializations=[
            (_FIRST, _MIDDLE),
            (_MIDDLE, _LAST),
            (_FOREIGN, Iri(value="urn:module:Independent")),
        ],
    )


def _seeds(*, ontology: OntologyClosure) -> tuple[OntologyTermReference, ...]:
    return tuple(term for term in ontology.documents[0].terms if term.term_iri in {_FIRST, _LAST})


@final
class _Extractor:
    capabilities = OntologyCapabilities(
        adapter_id="test/module",
        adapter_version="1.0",
        extraction=(
            ModuleExtractionSupport(
                method=ModuleExtractionMethod.STAR,
                profile=ReasoningProfile.OWL2_DL,
                regime=SemanticRegime.OWL_DIRECT,
                guarantee=ModuleGuarantee.SIGNATURE_ENTAILMENTS,
            ),
        ),
    )

    def __init__(self, *, misbound: bool = False, retain_source: bool = False) -> None:
        self._misbound = misbound
        self._retain_source = retain_source
        self.calls = 0

    async def extract(  # noqa: PLR0913 -- explicit adapter contract
        self,
        *,
        ontology: OntologyClosure,
        seeds: Sequence[OntologyTermReference],
        method: ModuleExtractionMethod,
        profile: ReasoningProfile,
        regime: SemanticRegime,
        ontology_iri: Iri,
        limits: OntologyLimits,
    ) -> OntologyModuleResult:
        self.calls += 1
        module = named_class_scope(
            identity=ontology_iri, specializations=[(_FIRST, _MIDDLE), (_MIDDLE, _LAST)]
        )
        signature = tuple(
            term
            for term in ontology.documents[0].terms
            if self._retain_source or term.term_iri in {_FIRST, _MIDDLE, _LAST}
        )
        if self._retain_source:
            module = _importing(ontology=ontology, ontology_iri=ontology_iri)
        return OntologyModuleResult(
            source_hash=module.content_hash if self._misbound else ontology.content_hash,
            ontology_iri=ontology_iri,
            limits=limits,
            seeds=seeds,
            method=method,
            profile=profile,
            regime=regime,
            adapter=self.capabilities,
            status=SemanticStatus.COMPLETE,
            guarantee=ModuleGuarantee.SIGNATURE_ENTAILMENTS,
            signature=signature,
            ontology=module,
            issues=(),
        )


def _importing(*, ontology: OntologyClosure, ontology_iri: Iri) -> OntologyClosure:
    payload = f"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <{ontology_iri.value}> a owl:Ontology ;
            owl:imports <{ontology.root.document_iri.value}> .
    """.encode()
    return load_ontology(
        document=OntologyDocument(
            pin=OntologyDocumentPin(
                document_iri=ontology_iri,
                ontology_iri=ontology_iri,
                content_hash=hash_bytes(content=payload),
            ),
            syntax=OntologySyntax.TURTLE,
            payload=payload,
        ),
        resources=tuple(parsed.document for parsed in ontology.documents),
    )


async def test_extraction_seals_and_validates_the_exact_attempt() -> None:
    source = _source()
    selected = list(_seeds(ontology=source))
    first = await extract_ontology_module(
        ontology=source,
        seeds=selected,
        method=ModuleExtractionMethod.STAR,
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        ontology_iri=_DERIVED,
        extractor=_Extractor(),
    )
    selected.clear()
    second = await extract_ontology_module(
        ontology=source,
        seeds=first.seeds,
        method=ModuleExtractionMethod.STAR,
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        ontology_iri=_DERIVED,
        extractor=_Extractor(),
        limits=OntologyLimits(timeout_ms=25_000),
    )
    assert first.status is SemanticStatus.COMPLETE
    assert first.guarantee is ModuleGuarantee.SIGNATURE_ENTAILMENTS
    assert first.ontology is not None
    assert first.ontology.root.ontology_iri == _DERIVED
    assert first.seeds == _seeds(ontology=source)
    assert second.fingerprint != first.fingerprint
    assert second.ontology == first.ontology
    mismatch = await extract_ontology_module(
        ontology=source,
        seeds=first.seeds,
        method=ModuleExtractionMethod.STAR,
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        ontology_iri=_DERIVED,
        extractor=_Extractor(misbound=True),
    )
    assert mismatch.status is SemanticStatus.FAILED
    assert mismatch.ontology is None
    assert mismatch.guarantee is ModuleGuarantee.NONE


async def test_unknown_seeds_and_unsupported_method_cannot_run_the_extractor() -> None:
    source = _source()
    known = _seeds(ontology=source)
    fake = _Extractor()
    unbound = replace(known[0], source=replace(source.root, document_iri=_DERIVED))
    with pytest.raises(ValueError, match="exact"):
        _ = await extract_ontology_module(
            ontology=source,
            seeds=[unbound],
            method=ModuleExtractionMethod.STAR,
            profile=ReasoningProfile.OWL2_DL,
            regime=SemanticRegime.OWL_DIRECT,
            ontology_iri=_DERIVED,
            extractor=fake,
        )
    unsupported = await extract_ontology_module(
        ontology=source,
        seeds=known,
        method=ModuleExtractionMethod.MIREOT,
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        ontology_iri=_DERIVED,
        extractor=fake,
    )
    assert unsupported.status is SemanticStatus.UNSUPPORTED
    assert unsupported.ontology is None
    assert unsupported.guarantee is ModuleGuarantee.NONE
    assert fake.calls == 0


async def test_retained_source_imports_and_bounds_cannot_claim_a_standalone_module() -> None:
    source = _source()
    engine = _Extractor(retain_source=True)
    retained = await extract_ontology_module(
        ontology=source,
        seeds=_seeds(ontology=source),
        method=ModuleExtractionMethod.STAR,
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        ontology_iri=_DERIVED,
        extractor=engine,
    )
    assert retained.status is SemanticStatus.COMPLETE
    assert retained.guarantee is ModuleGuarantee.NONE
    assert retained.ontology is not None
    (binding,) = retained.ontology.imports
    assert binding.target == source.root
    assert retained.issues[0].code == "module_retains_source_imports"

    bounded = await extract_ontology_module(
        ontology=source,
        seeds=_seeds(ontology=source),
        method=ModuleExtractionMethod.STAR,
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        ontology_iri=_DERIVED,
        extractor=engine,
        limits=OntologyLimits(max_statements=1),
    )
    assert bounded.status is SemanticStatus.INCOMPLETE
    assert bounded.ontology is None
    assert engine.calls == 1


async def test_robot_star_preserves_seed_entailments_and_excludes_unrelated_axioms() -> None:
    from examples.notebooks.robot_modules import RobotModuleExtractor  # noqa: PLC0415

    provisioned = os.environ.get(ROBOT_ENV)
    if provisioned is None:
        pytest.skip("Provision the pinned ROBOT JAR for engine conformance")
    jar = Path(provisioned)
    source = _source()
    seeds = _seeds(ontology=source)
    result = await extract_ontology_module(
        ontology=source,
        seeds=seeds,
        method=ModuleExtractionMethod.STAR,
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        ontology_iri=_DERIVED,
        extractor=RobotModuleExtractor(jar=jar),
    )
    assert result.status is SemanticStatus.COMPLETE, result.issues
    assert result.guarantee is ModuleGuarantee.SIGNATURE_ENTAILMENTS
    assert result.ontology is not None
    assert result.ontology.imports == ()
    assert set(seeds) <= set(result.signature)
    assert _FOREIGN not in {term.term_iri for term in result.signature}
    assert any(term.term_iri == _FOREIGN for term in source.documents[0].terms)
    query = ReasoningRequest(
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        task=ReasoningTask.ENTAILMENT,
        query=named_class_scope(
            identity=Iri(value="urn:module:query"), specializations=[(_FIRST, _LAST)]
        ),
    )
    reasoner = RobotReasoner(jar=jar)
    before = await reason_ontology(ontology=source, request=query, reasoner=reasoner)
    after = await reason_ontology(ontology=result.ontology, request=query, reasoner=reasoner)
    assert before.entailed is after.entailed is True
    assert before.fingerprint != after.fingerprint
