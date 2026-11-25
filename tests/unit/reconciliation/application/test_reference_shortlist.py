"""Keep optional reference suggestions consistent with reviewed endpoint direction."""

from domain_kernel import (
    CardinalityBounds,
    Definition,
    DefinitionId,
    ModelId,
    ModelScope,
    ProjectId,
    ReferenceDefinition,
    ReferenceDefinitionId,
    RelationshipCardinality,
    RelationshipDefinition,
)
from domain_kernel.reconciliation.application.matcher import EvidenceBasedConceptMatcher


def test_reference_shortlist_uses_reviewed_endpoint_pairs() -> None:
    local_actor, local_object = DefinitionId(value="actor"), DefinitionId(value="object")
    ref_actor, ref_object = (
        ReferenceDefinitionId(value="actor"),
        ReferenceDefinitionId(value="object"),
    )
    bounds = RelationshipCardinality(
        outgoing=CardinalityBounds(maximum=None), incoming=CardinalityBounds(maximum=None)
    )
    scope = ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="model"))
    local = Definition(
        id=DefinitionId(value="sends"),
        scope=scope,
        revision=1,
        name="sends",
        display_name="Sends",
        meaning="An actor sends an object.",
        body=RelationshipDefinition(
            source_concept_id=local_actor, target_concept_id=local_object, cardinality=bounds
        ),
    )
    direct = ReferenceDefinition(
        id=ReferenceDefinitionId(value="direct"),
        name="sends",
        meaning="Sends the object.",
        provenance="curated",
        body=RelationshipDefinition(
            source_concept_id=ref_actor, target_concept_id=ref_object, cardinality=bounds
        ),
    )
    reversed_roles = ReferenceDefinition(
        id=ReferenceDefinitionId(value="reversed"),
        name="sends",
        meaning="The inverse candidate.",
        provenance="curated",
        body=RelationshipDefinition(
            source_concept_id=ref_object, target_concept_id=ref_actor, cardinality=bounds
        ),
    )
    matcher = EvidenceBasedConceptMatcher()
    members = [direct, reversed_roles]
    assert {c.target.id for c in matcher.reference(local=local, members=members)} == {
        direct.id,
        reversed_roles.id,
    }
    candidates = matcher.reference(
        local=local,
        members=members,
        endpoint_alignments={local_actor: ref_actor, local_object: ref_object},
    )
    assert [c.target.id for c in candidates] == [direct.id]
