from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.contracts import (
    ModelScope,
    ModelVersion,
    PinnedDefinitionReference,
)
from domain_kernel.shared.domain.data_shapes import (
    AttributeDefinition,
    ConceptReferenceType,
    QuantityBinding,
    StructuredValueType,
    ValueSetType,
)
from domain_kernel.shared.domain.definitions import (
    ConceptDefinition,
    Definition,
    RelationshipDefinition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
    ValueSetMember,
)
from domain_kernel.shared.domain.model_values import (
    BusinessCode,
    LabelText,
    MeaningText,
    RelationshipCardinality,
    ValueSetMembership,
)
from domain_kernel.shared.domain.shape_graph import (
    remap_shape,
    shape_references,
    validate_body_graph,
    validate_model_shapes,
)
from domain_kernel.shared.identifiers.content_hash import ContentHash

if TYPE_CHECKING:
    from domain_kernel.shared.contracts import DefinitionReference


_SCOPE = ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="recruitment"))


def _quantity_model(
    *, unit_reference: DefinitionReference
) -> tuple[Definition[ValueSetDefinition], Definition[StructuredValueDefinition]]:
    vocabulary = Definition(
        id=DefinitionId(value="units"),
        name="duration-units",
        display_name="Duration units",
        meaning="Application duration codes.",
        scope=_SCOPE,
        revision=1,
        body=ValueSetDefinition(
            membership=ValueSetMembership.CLOSED,
            members=[
                ValueSetMember(
                    code=BusinessCode(value="h"),
                    label=LabelText(value="Hour"),
                    meaning=MeaningText(value="Hour of processing."),
                    unit=unit_reference,
                )
            ],
        ),
    )
    magnitude = AttributeDefinition.decimal(name="magnitude", required=True)
    unit_field = AttributeDefinition.value_set(
        name="unit",
        required=True,
        value_set=vocabulary.id,
    )
    duration = Definition(
        id=DefinitionId(value="duration"),
        name="processing-duration",
        display_name="Processing duration",
        meaning="An application duration with a selected unit.",
        scope=_SCOPE,
        revision=1,
        body=StructuredValueDefinition(
            attributes=[magnitude, unit_field],
            quantity=QuantityBinding(magnitude=magnitude.id, unit=unit_field.id),
        ),
    )
    return vocabulary, duration


def _unit(*, scope: ModelScope = _SCOPE) -> Definition[UnitDefinition]:
    return Definition(
        id=DefinitionId(value="hour"),
        name="hour",
        display_name="Hour",
        meaning="Unit of application processing duration.",
        scope=scope,
        revision=1,
        body=UnitDefinition(symbol="h"),
    )


def test_graph_checks_active_kind_and_closed_quantity_set() -> None:
    unit = _unit()
    vocabulary, duration = _quantity_model(unit_reference=unit.id)

    assert validate_model_shapes(scope=_SCOPE, definitions=[unit, vocabulary, duration]) == ()
    dangling = validate_model_shapes(
        scope=_SCOPE,
        definitions=[replace(unit, status=DefinitionStatus.RETIRED), vocabulary, duration],
    )
    wrong_kind = validate_model_shapes(
        scope=_SCOPE, definitions=[replace(unit, body=ConceptDefinition()), vocabulary, duration]
    )
    open_set = validate_model_shapes(
        scope=_SCOPE,
        definitions=[
            unit,
            replace(vocabulary, body=replace(vocabulary.body, membership=ValueSetMembership.OPEN)),
            duration,
        ],
    )
    assert tuple(issue.code for issue in dangling) == ("unresolved_shape_reference",)
    assert tuple(issue.code for issue in wrong_kind) == ("shape_reference_kind",)
    assert tuple(issue.code for issue in open_set) == ("quantity_units_not_closed",)


def test_graph_requires_the_exact_dependency_pin_and_revision() -> None:
    external_scope = replace(_SCOPE, model_id=ModelId(value="shared-units"))
    hour = _unit(scope=external_scope)
    version = ModelVersion(
        scope=external_scope,
        version="1.0.0",
        content_hash=ContentHash(value="sha256:" + "0" * 64),
    )
    pin = PinnedDefinitionReference(
        model=version,
        definition_id=hour.id,
        definition_revision=hour.revision,
    )
    vocabulary, duration = _quantity_model(unit_reference=pin)
    assert (
        validate_model_shapes(
            scope=_SCOPE,
            definitions=[vocabulary, duration],
            dependencies={pin: hour},
        )
        == ()
    )
    issues = validate_model_shapes(
        scope=_SCOPE,
        definitions=[vocabulary, duration],
        dependencies={pin: replace(hour, revision=2)},
    )
    assert "shape_dependency_mismatch" in {issue.code for issue in issues}


def test_model_shape_graph_rejects_even_exact_cross_project_pins() -> None:
    external_scope = replace(_SCOPE, project_id=ProjectId(value="another-project"))
    hour = _unit(scope=external_scope)
    version = ModelVersion(
        scope=external_scope,
        version="1.0.0",
        content_hash=ContentHash(value="sha256:" + "0" * 64),
    )
    pin = PinnedDefinitionReference(model=version, definition_id=hour.id, definition_revision=1)
    vocabulary, duration = _quantity_model(unit_reference=pin)
    issues = validate_model_shapes(
        scope=_SCOPE,
        definitions=[vocabulary, duration],
        dependencies={pin: hour},
    )
    assert "shape_dependency_mismatch" in {issue.code for issue in issues}


def test_pack_and_company_edges_require_their_own_nominal_reference_types() -> None:
    pack_unit = ReferenceDefinitionId(value="hour")
    pack_units = ReferenceDefinitionId(value="units")
    vocabulary, duration = _quantity_model(unit_reference=pack_unit)
    assert validate_body_graph(bodies={pack_units: vocabulary.body, pack_unit: _unit().body}) == ()
    issues = validate_model_shapes(scope=_SCOPE, definitions=[vocabulary, duration])
    assert tuple(issue.code for issue in issues) == ("shape_reference_context",)


def test_concept_reference_and_relationship_endpoint_rewrites_share_the_traversal() -> None:
    old = DefinitionId(value="system")
    new = DefinitionId(value="reviewed-system")
    attribute = AttributeDefinition.reference(target=old, name="system")
    concept = ConceptDefinition(attributes=[attribute])
    relationship = RelationshipDefinition(
        source_concept_id=old,
        target_concept_id=old,
        cardinality=RelationshipCardinality.one_to_many(),
    )
    for body in (concept, relationship):
        rewritten = remap_shape(body=body, replacements={old: new})
        assert {edge.target for edge in shape_references(body=rewritten)} == {new}
    assert attribute.value_type == ConceptReferenceType(concept=old)


def test_traversal_and_remapping_agree_on_exact_edges() -> None:
    vocabulary, duration = _quantity_model(unit_reference=DefinitionId(value="hour"))
    unit_edges = shape_references(body=vocabulary.body)
    assert len(unit_edges) == 1
    assert (unit_edges[0].target, unit_edges[0].expected_kind) == (
        DefinitionId(value="hour"),
        DefinitionKind.UNIT,
    )
    assert unit_edges[0].path == ("members", 0, "unit")
    replacement = DefinitionId(value="new-units")
    duration_edges = shape_references(body=duration.body)
    assert len(duration_edges) == 1
    assert duration_edges[0].closed_vocabulary
    rewritten = remap_shape(body=duration.body, replacements={vocabulary.id: replacement})
    assert isinstance(rewritten, StructuredValueDefinition)
    assert rewritten.attributes[1].value_type == ValueSetType(value_set=replacement)
    assert rewritten.attributes[1].id == duration.body.attributes[1].id
    assert rewritten.quantity == duration.body.quantity
    assert duration.body.attributes[1].value_type == ValueSetType(value_set=vocabulary.id)


def test_structured_embedding_cycles_fail_and_relationship_cycles_pass() -> None:
    first = DefinitionId(value="first")
    second = DefinitionId(value="second")
    a = Definition(
        id=first,
        scope=_SCOPE,
        revision=1,
        name="first",
        display_name="First",
        meaning="First value",
        body=StructuredValueDefinition(
            attributes=[
                AttributeDefinition(
                    name="second", value_type=StructuredValueType(structure=second)
                ),
            ],
        ),
    )
    b = replace(
        a,
        id=second,
        name="second",
        display_name="Second",
        body=StructuredValueDefinition(
            attributes=[
                AttributeDefinition(name="first", value_type=StructuredValueType(structure=first)),
            ],
        ),
    )
    assert tuple(
        issue.code for issue in validate_model_shapes(scope=_SCOPE, definitions=[a, b])
    ) == ("cyclic_structured_embedding",)

    a_concept = replace(a, body=ConceptDefinition())
    b_concept = replace(b, body=ConceptDefinition())
    relation = Definition(
        id=DefinitionId(value="a-to-b"),
        scope=_SCOPE,
        revision=1,
        name="a-to-b",
        display_name="A to B",
        meaning="A relates to B",
        body=RelationshipDefinition(
            source_concept_id=first,
            target_concept_id=second,
            cardinality=RelationshipCardinality.many_to_one(),
        ),
    )
    reverse = replace(
        relation,
        id=DefinitionId(value="b-to-a"),
        name="b-to-a",
        body=replace(relation.body, source_concept_id=second, target_concept_id=first),
    )
    assert (
        validate_model_shapes(scope=_SCOPE, definitions=[a_concept, b_concept, relation, reverse])
        == ()
    )
