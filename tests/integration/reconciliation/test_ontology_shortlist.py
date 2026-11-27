"""Compare deterministic predicate suggestions on a fixed, pinned mapping panel."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from domain_kernel import (
    CardinalityBounds,
    ConceptDefinition,
    Definition,
    DefinitionId,
    Iri,
    ModelId,
    ModelScope,
    OntologyDocument,
    OntologyDocumentPin,
    OntologySyntax,
    ProjectId,
    ReferenceDefinition,
    ReferenceDefinitionId,
    ReferencePack,
    ReferencePackSpec,
    RelationshipCardinality,
    RelationshipDefinition,
    load_ontology,
)
from domain_kernel.reconciliation.application.matcher import EvidenceBasedConceptMatcher
from domain_kernel.reconciliation.application.ontology_shortlist import OntologyShortlist
from domain_kernel.shared.hashing import Hashing

pytestmark = pytest.mark.integration

_BOUNDS = RelationshipCardinality(
    outgoing=CardinalityBounds(maximum=None), incoming=CardinalityBounds(maximum=None)
)
_SCOPE = ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="model"))
_TURTLE = b"""
@prefix ex: <https://example.test/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Actor a owl:Class .
ex:Specialist a owl:Class ; rdfs:subClassOf ex:Actor .
ex:Record a owl:Class .
ex:finalizes a owl:ObjectProperty ; rdfs:domain ex:Actor ; rdfs:range ex:Record ;
  owl:inverseOf ex:isFinalizedBy .
ex:isFinalizedBy a owl:ObjectProperty ; rdfs:domain ex:Record ; rdfs:range ex:Actor .
"""
_TERMS = ("finalizes", "isFinalizedBy")
# Expected mappings come from the directed source meaning and the authored pack.
_PANEL = (
    ("direct", "finalizes", "Actor", "Record", "forward"),
    ("direct-label", "finalizes", "Actor", "Record", "forward"),
    ("subtype", "finalizes", "Specialist", "Record", "forward"),
    ("subtype-label", "finalizes", "Specialist", "Record", "forward"),
    ("declared-inverse", "is-finalized-by", "Record", "Actor", "inverse"),
    ("inverse-subtype", "is-finalized-by", "Record", "Specialist", "inverse"),
    ("wrong-direction", "finalizes", "Record", "Actor", None),
    ("unknown-actor", "finalizes", None, "Record", "forward"),
    ("unknown-record", "is-finalized-by", None, "Actor", "inverse"),
    ("out-of-schema", "audits", "Actor", "Record", None),
    ("out-of-schema-inverse", "is-audited-by", "Record", "Actor", None),
    ("out-of-schema-untyped", "archives", None, None, None),
)


def _pack() -> ReferencePack:
    closure = load_ontology(
        document=OntologyDocument(
            syntax=OntologySyntax.TURTLE,
            pin=OntologyDocumentPin(
                document_iri=Iri(value="https://example.test/pinned.ttl"),
                content_hash=Hashing.hash_bytes(content=_TURTLE),
            ),
            payload=_TURTLE,
        )
    )
    terms = {
        term.term_iri.value.rsplit("/", maxsplit=1)[1]: term for term in closure.documents[0].terms
    }
    concepts = [
        ReferenceDefinition(
            id=ReferenceDefinitionId(value=name),
            name=name.lower(),
            meaning=name,
            provenance="curated",
            body=ConceptDefinition(),
            ontology_terms=[terms[name]],
        )
        for name in ("Actor", "Specialist", "Record")
    ]
    edges = [
        ReferenceDefinition(
            id=ReferenceDefinitionId(value=identity),
            name=label,
            meaning=meaning,
            provenance="curated",
            ontology_terms=[terms[term]],
            body=RelationshipDefinition(
                source_concept_id=ReferenceDefinitionId(value=source),
                target_concept_id=ReferenceDefinitionId(value=target),
                cardinality=_BOUNDS,
            ),
        )
        for identity, label, meaning, term, source, target in (
            ("forward", "finalizes", "Actor finalizes a record.", _TERMS[0], "Actor", "Record"),
            (
                "inverse",
                "record-completed",
                "A record is finalized by an actor.",
                _TERMS[1],
                "Record",
                "Actor",
            ),
            (
                "distractor",
                "finalizes-record",
                "Reversed distractor.",
                _TERMS[0],
                "Record",
                "Actor",
            ),
        )
    ]
    result = ReferencePack.compose(
        spec=ReferencePackSpec(
            key="review.shortlist",
            version="1.0.0",
            title="Review vocabulary",
            applicability="Review records.",
            provenance="Authored directional fixtures.",
            license="Apache-2.0",
            definitions=[*concepts, *edges],
            ontologies=[closure],
        ),
        actor="editor",
        reason="Pin the benchmark terminology.",
    )
    assert result.pack is not None, result.validation.issues
    return result.pack


@dataclass(frozen=True)
class MappingResult:
    """Expected predicate and ordered suggestions for one authored case."""

    case: str
    expected: str | None
    baseline: tuple[str, ...]
    candidate: tuple[str, ...]


def evaluate_panel() -> tuple[MappingResult, ...]:
    """Return the ordered candidates for all twelve fixed examples."""
    pack = _pack()
    ontology = OntologyShortlist(pack=pack, members=pack.definitions)
    matcher = EvidenceBasedConceptMatcher()
    rows: list[MappingResult] = []
    for case, predicate, source, target, expected in _PANEL:
        local_source, local_target = DefinitionId("source"), DefinitionId("target")
        local = Definition(
            id=DefinitionId(value=case),
            scope=_SCOPE,
            revision=1,
            name=predicate,
            display_name=predicate.replace("-", " "),
            meaning=f"Source {predicate} target.",
            body=RelationshipDefinition(
                source_concept_id=local_source, target_concept_id=local_target, cardinality=_BOUNDS
            ),
        )
        pins = {
            local_id: ReferenceDefinitionId(value=reference)
            for local_id, reference in ((local_source, source), (local_target, target))
            if reference is not None
        }
        baseline = matcher.reference(
            local=local, members=pack.definitions, endpoint_alignments=pins
        )
        candidate = matcher.reference(
            local=local, members=pack.definitions, endpoint_alignments=pins, ontology=ontology
        )
        rows.append(
            MappingResult(
                case,
                expected,
                tuple(c.target.id.value for c in baseline),
                tuple(c.target.id.value for c in candidate),
            )
        )
    return tuple(rows)


def test_pinned_ontology_shortlist_finds_expected_directions() -> None:
    rows = evaluate_panel()
    assert len(rows) == len(_PANEL)
    assert all((row.candidate[0] if row.candidate else None) == row.expected for row in rows), rows
