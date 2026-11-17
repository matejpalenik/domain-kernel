"""Opt-in OWLAPI STAR extraction over verified named-class inputs."""

from __future__ import annotations

from asyncio import to_thread
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, final

from domain_kernel import (
    ModuleExtractionMethod,
    ModuleExtractionSupport,
    ModuleGuarantee,
    OntologyCapabilities,
    OntologyDocument,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologyModuleResult,
    OntologySyntax,
    ReasoningProfile,
    SemanticRegime,
    SemanticStatus,
    UnsupportedCapabilityError,
    load_ontology,
)
from domain_kernel.shared.hashing import hash_bytes
from examples.notebooks.robot_reasoner import RobotProcess, asserted_operations, write_operations

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel import Iri, OntologyClosure, OntologyLimits, OntologyTermReference

_SUPPORT = ModuleExtractionSupport(
    method=ModuleExtractionMethod.STAR,
    profile=ReasoningProfile.OWL2_DL,
    regime=SemanticRegime.OWL_DIRECT,
    guarantee=ModuleGuarantee.SIGNATURE_ENTAILMENTS,
)


@final
class RobotModuleExtractor:
    """Extract a standalone locality module and preserve the source term identities."""

    def __init__(self, *, jar: Path) -> None:
        """Bind the pinned engine and advertise the tested STAR combination."""
        self._process = RobotProcess(jar=jar)
        self.capabilities = OntologyCapabilities(
            adapter_id="robot/owlapi-locality",
            adapter_version=self._process.version,
            extraction=(_SUPPORT,),
            feature_ids=("named-class-fragment", "rdfxml-module"),
        )

    async def extract(  # noqa: PLR0913 -- exact adapter options are required
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
        """Run STAR against the complete selection and read its standalone RDF/XML."""
        if (method, profile, regime) != (_SUPPORT.method, _SUPPORT.profile, _SUPPORT.regime):
            raise UnsupportedCapabilityError
        if any(seed.entity_kind is not OntologyEntityKind.CLASS for seed in seeds):
            raise UnsupportedCapabilityError
        asserted = asserted_operations(ontology=ontology)
        with TemporaryDirectory(prefix="domain-kernel-module-") as directory:
            root = Path(directory)
            source = root / "asserted.tsv"
            selection = root / "selected.tsv"
            write_operations(operations=asserted, path=source)
            _ = selection.write_text(
                "".join(
                    f"{iri.value}\n" for iri in (ontology_iri, *(seed.term_iri for seed in seeds))
                ),
                encoding="utf-8",
            )
            payload = await self._process.run(
                task=method.value, source=source, selection=selection, bytes_limit=limits.max_bytes
            )
        if payload.strip() == b"unsupported":
            raise UnsupportedCapabilityError
        module = await to_thread(
            load_ontology,
            document=OntologyDocument(
                pin=OntologyDocumentPin(
                    document_iri=ontology_iri,
                    ontology_iri=ontology_iri,
                    content_hash=hash_bytes(content=payload),
                ),
                syntax=OntologySyntax.RDFXML,
                payload=payload,
            ),
            limits=limits,
        )
        declarations = {
            (term.term_iri, term.entity_kind) for item in module.documents for term in item.terms
        }
        signature = tuple(
            term
            for item in ontology.documents
            for term in item.terms
            if (term.term_iri, term.entity_kind) in declarations
        )
        return OntologyModuleResult(
            source_hash=ontology.content_hash,
            ontology_iri=ontology_iri,
            limits=limits,
            seeds=seeds,
            method=method,
            profile=profile,
            regime=regime,
            adapter=self.capabilities,
            status=SemanticStatus.COMPLETE,
            guarantee=_SUPPORT.guarantee,
            signature=signature,
            ontology=module,
            issues=(),
        )
