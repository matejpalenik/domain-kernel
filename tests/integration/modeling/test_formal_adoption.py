"""Proof of reviewed asserted semantics and exact preservation through archives."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AttributeDefinition,
    Client,
    ClientConfiguration,
    DomainModelBuilder,
    DomainModelBundle,
    InvalidDecisionError,
    Iri,
    ModelKind,
    ModelTermReference,
    OntologyDocument,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologyModuleDefinition,
    OntologySyntax,
    PinnedDefinitionReference,
    SemanticLinkDefinition,
    SemanticRelation,
    TraversalDirection,
    compose_models,
    load_ontology,
    slice_model,
)
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
pytest.importorskip("rdflib")


async def test_reviewed_modules_and_links_survive_publication_slice_and_copy(
    tmp_path: Path,
) -> None:
    raw = b"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix ext: <https://example.org/vocabulary#> .
        <https://example.org/vocabulary> a owl:Ontology .
        ext:System a owl:Class ;
            owl:equivalentClass [
                a owl:Restriction ; owl:onProperty ext:purpose ; owl:someValuesFrom owl:Thing
            ] .
    """
    source = OntologyDocument(
        pin=OntologyDocumentPin(
            document_iri=Iri(value="https://example.org/vocabulary.ttl"),
            ontology_iri=Iri(value="https://example.org/vocabulary"),
            content_hash=Hashing.hash_bytes(content=raw),
        ),
        syntax=OntologySyntax.TURTLE,
        payload=raw,
    )
    closure = load_ontology(document=source)
    external = closure.documents[0].terms[0]
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="editor",
        name="recruitment",
    )
    model = await project.create_model(
        actor="editor",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Recruitment specializations.",
    )
    builder = DomainModelBuilder(model_info=model.info)
    module = builder.add_definition(
        name="system-ontology",
        meaning="Reviewed system restriction.",
        body=OntologyModuleDefinition(ontology=closure),
    )
    field = AttributeDefinition.string(name="purpose")
    local = builder.add_concept(
        name="recruitment-system",
        meaning="A recruitment system.",
        attributes=[field],
    )
    local_term = ModelTermReference(definition=local, entity_kind=OntologyEntityKind.CLASS)
    link = builder.add_definition(
        name="system-specialisation",
        meaning="Recruitment is a kind of system.",
        body=SemanticLinkDefinition(
            subject=local_term,
            relation=SemanticRelation.SUBCLASS_OF,
            object=external,
        ),
    )
    _ = builder.add_definition(
        name="purpose-documentation",
        meaning="Document the meaning of the authored purpose field.",
        body=SemanticLinkDefinition(
            subject=ModelTermReference(
                definition=local,
                entity_kind=OntologyEntityKind.DATA_PROPERTY,
                local_path=("attributes", field.id.value),
            ),
            relation=SemanticRelation.SEE_ALSO,
            object=external,
        ),
    )
    related = builder.add_concept(
        name="recruitment-automation",
        meaning="The same system considered as an automation.",
    )
    related_term = ModelTermReference(definition=related, entity_kind=OntologyEntityKind.CLASS)
    for name, subject, target in (
        ("recruitment-automation-parent", local_term, related_term),
        ("automation-recruitment-parent", related_term, local_term),
    ):
        _ = builder.add_definition(
            name=name,
            meaning="Preserve the reviewed direct class assertion.",
            body=SemanticLinkDefinition(
                subject=subject,
                relation=SemanticRelation.SUBCLASS_OF,
                object=target,
            ),
        )
    with pytest.raises(ValueError, match="skos_concept"):
        _ = SemanticLinkDefinition(
            subject=local_term,
            relation=SemanticRelation.EXACT_MATCH,
            object=related_term,
        )
    plan = builder.build_change_plan(reason="Adopt the exact system axioms and classify locally.")
    case = await model.propose_change_plan(actor="editor", plan=plan)
    approved = Accept(reason="The exact source and local endpoints have been reviewed.")
    assert not (await model.preview_changes(case=case, decision=approved)).blockers
    _ = await model.decide_review(actor="reviewer", case=case, decision=approved)
    prepared = await model.prepare_publication(actor="editor")
    bundle = await model.publish(
        publication=prepared,
        version="1.0.0",
        actor="publisher",
        reason="Send verified assertions.",
    )
    reopened = DomainModelBundle.deserialize(payload=bundle.serialize())
    assert reopened == bundle
    forms = {
        entry.name
        for entry in reopened.content.definitions
        if isinstance(entry.body, SemanticLinkDefinition)
    }
    assert forms == {
        "purpose-documentation",
        "system-specialisation",
        "recruitment-automation-parent",
        "automation-recruitment-parent",
    }

    sliced = slice_model(
        composition=compose_models(bundles=[reopened]),
        seeds=[
            PinnedDefinitionReference(
                model=reopened.model_version,
                definition_id=link,
                definition_revision=1,
            )
        ],
        max_hops=0,
        direction=TraversalDirection.OUTGOING,
    )
    assert sliced.ontologies == (closure,)
    assert {entry.definition.id for entry in sliced.support} == {module, local}
    assert closure.documents[0].document.payload == raw

    current = await project.get_model(name=model.info.name)
    builder = DomainModelBuilder(model_info=current.info)
    builder.remove_definition(definition=await current.get_definition(definition_id=module))
    with pytest.raises(InvalidDecisionError) as blocked:
        _ = await current.propose_change_plan(
            actor="editor",
            plan=builder.build_change_plan(reason="Retire upstream selection."),
        )
    assert "ontology_term_missing" in {issue.code for issue in blocked.value.issues}
    assert await model.get_version(version=bundle.version) == bundle

    copied = await project.create_model(
        actor="editor",
        name="redesign",
        kind=ModelKind.PROPOSED,
        description="Retain formal semantics in a redesign.",
        copy_from=reopened,
    )
    authored_property_link = await copied.get_definition(name="purpose-documentation")
    concept = await copied.get_concept(name="recruitment-system")
    assert isinstance(authored_property_link.body, SemanticLinkDefinition)
    assert authored_property_link.body.subject == ModelTermReference(
        definition=concept.id,
        entity_kind=OntologyEntityKind.DATA_PROPERTY,
        local_path=("attributes", concept.get_attribute(name="purpose").id.value),
    )
