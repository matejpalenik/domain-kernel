"""Pure reference traversal and validation for captured business definitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, assert_never

from domain_kernel._shared.domain.data_shapes import (
    ConceptReferenceType,
    ScalarValueType,
    StructuredValueType,
    ValueSetType,
    replace_attribute_type,
)
from domain_kernel._shared.domain.definitions import (
    ConceptDefinition,
    RelationshipDefinition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
)
from domain_kernel._shared.domain.model_values import ValueSetMembership
from domain_kernel._shared.domain.ontology_assets import require_unit_term
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.contracts import Issue, PinnedDefinitionReference

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from domain_kernel._shared.domain.data_shapes import AttributeType
    from domain_kernel._shared.domain.definitions import Definition, DefinitionBody
    from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
    from domain_kernel.shared.contracts import DefinitionReference, ModelScope, ModelVersion


@dataclass(frozen=True, kw_only=True)
class ShapeReference:
    """One typed edge plus its path within the owning body."""

    target: DefinitionReference
    expected_kind: DefinitionKind
    path: tuple[str | int, ...]
    closed_vocabulary: bool = False


type _VisitReference = Callable[[ShapeReference], DefinitionReference]
type _DependencyIndex = Mapping[tuple[ModelVersion, DefinitionId], PinnedDefinitionReference]


def _visit_attribute_type(
    *,
    value_type: AttributeType,
    path: tuple[str | int, ...],
    closed_vocabulary: bool,
    visit: _VisitReference,
) -> AttributeType:
    match value_type:
        case ScalarValueType():
            return value_type
        case ConceptReferenceType(concept=target):
            mapped = visit(
                ShapeReference(
                    target=target,
                    path=(*path, "concept"),
                    expected_kind=DefinitionKind.CONCEPT,
                )
            )
            return value_type if mapped == target else replace(value_type, concept=mapped)
        case ValueSetType(value_set=target):
            mapped = visit(
                ShapeReference(
                    target=target,
                    path=(*path, "value_set"),
                    expected_kind=DefinitionKind.VALUE_SET,
                    closed_vocabulary=closed_vocabulary,
                )
            )
            return value_type if mapped == target else replace(value_type, value_set=mapped)
        case StructuredValueType(structure=target):
            mapped = visit(
                ShapeReference(
                    target=target,
                    path=(*path, "structure"),
                    expected_kind=DefinitionKind.STRUCTURED_VALUE,
                )
            )
            return value_type if mapped == target else replace(value_type, structure=mapped)
        case _:
            assert_never(value_type)


def _visit_body(*, body: DefinitionBody, visit: _VisitReference) -> DefinitionBody:
    match body:
        case ConceptDefinition() | StructuredValueDefinition():
            unit_field: AttributeId | None = None
            if isinstance(body, StructuredValueDefinition) and body.quantity is not None:
                unit_field = body.quantity.unit
            attributes = tuple(
                replace_attribute_type(
                    attribute=attribute,
                    value_type=_visit_attribute_type(
                        value_type=attribute.value_type,
                        path=("attributes", index, "value_type"),
                        closed_vocabulary=attribute.id == unit_field,
                        visit=visit,
                    ),
                )
                for index, attribute in enumerate(body.attributes)
            )
            return body if attributes == body.attributes else replace(body, attributes=attributes)
        case RelationshipDefinition():
            source = visit(
                ShapeReference(
                    target=body.source_concept_id,
                    path=("source_concept_id",),
                    expected_kind=DefinitionKind.CONCEPT,
                )
            )
            target = visit(
                ShapeReference(
                    target=body.target_concept_id,
                    path=("target_concept_id",),
                    expected_kind=DefinitionKind.CONCEPT,
                )
            )
            if source == body.source_concept_id and target == body.target_concept_id:
                return body
            return replace(body, source_concept_id=source, target_concept_id=target)
        case ValueSetDefinition():
            members = tuple(
                member
                if member.unit is None
                else replace(
                    member,
                    unit=visit(
                        ShapeReference(
                            target=member.unit,
                            path=("members", index, "unit"),
                            expected_kind=DefinitionKind.UNIT,
                        )
                    ),
                )
                for index, member in enumerate(body.members)
            )
            return body if members == body.members else replace(body, members=members)
        case UnitDefinition():
            return body
        case _:
            assert_never(body)


def shape_references(*, body: DefinitionBody) -> tuple[ShapeReference, ...]:
    """List the definition edges in one body, in record order."""
    edges: list[ShapeReference] = []

    def collect(edge: ShapeReference) -> DefinitionReference:
        edges.append(edge)
        return edge.target

    _ = _visit_body(body=body, visit=collect)
    return tuple(edges)


def remap_shape(
    *,
    body: DefinitionBody,
    replacements: Mapping[DefinitionReference, DefinitionReference],
) -> DefinitionBody:
    """Replace exact definition references while retaining local child identities."""
    return _visit_body(body=body, visit=lambda edge: replacements.get(edge.target, edge.target))


def _reference_path(*, owner: DefinitionReference, edge: ShapeReference) -> tuple[str | int, ...]:
    identifier = (
        owner.definition_id.value if isinstance(owner, PinnedDefinitionReference) else owner.value
    )
    return ("definitions", identifier, *edge.path)


def _edge_issue(
    *,
    owner: DefinitionReference,
    edge: ShapeReference,
    target: DefinitionBody | None,
) -> Issue | None:
    path = _reference_path(owner=owner, edge=edge)
    if isinstance(owner, ReferenceDefinitionId) != isinstance(edge.target, ReferenceDefinitionId):
        return Issue(
            code="shape_reference_context",
            path=path,
            message="Use a typed reference belonging to the owning model or reference pack.",
        )
    if target is None:
        return Issue(
            code="unresolved_shape_reference",
            path=path,
            message="Supply this active definition or its exact dependency pin.",
        )
    if target.kind is not edge.expected_kind:
        return Issue(
            code="shape_reference_kind",
            path=path,
            message=f"Use an active {edge.expected_kind.value} definition for this reference.",
        )
    if edge.closed_vocabulary and isinstance(target, ValueSetDefinition):
        return _quantity_set_issue(vocabulary=target, path=path)
    return None


def _quantity_set_issue(
    *, vocabulary: ValueSetDefinition, path: tuple[str | int, ...]
) -> Issue | None:
    if vocabulary.membership is not ValueSetMembership.CLOSED:
        return Issue(
            code="quantity_units_not_closed",
            path=path,
            message="Select a closed value set for the quantity unit field.",
        )
    for member in vocabulary.members:
        if member.ontology_term is not None:
            try:
                require_unit_term(term=member.ontology_term)
            except ValueError:
                return Issue(
                    code="quantity_unit_term_kind",
                    path=path,
                    message="Use individual or SKOS concept terms for inline quantity units.",
                )
    return None


def _qualify_target(
    *,
    owner: DefinitionReference,
    target: DefinitionReference,
    dependency_index: _DependencyIndex,
) -> DefinitionReference | None:
    if isinstance(owner, PinnedDefinitionReference) and isinstance(target, DefinitionId):
        return dependency_index.get((owner.model, target))
    return target


def validate_body_graph(
    *, bodies: Mapping[DefinitionReference, DefinitionBody]
) -> tuple[Issue, ...]:
    """Check typed edges in an explicitly captured active graph."""
    dependency_index = {
        (ref.model, ref.definition_id): ref
        for ref in bodies
        if isinstance(ref, PinnedDefinitionReference)
    }
    embedding: TopologicalSorter[DefinitionReference] = TopologicalSorter()
    issues: list[Issue] = []
    for owner, body in bodies.items():
        for edge in shape_references(body=body):
            target_ref = _qualify_target(
                owner=owner,
                target=edge.target,
                dependency_index=dependency_index,
            )
            target = bodies.get(target_ref) if target_ref is not None else None
            issue = _edge_issue(owner=owner, edge=edge, target=target)
            if issue is not None:
                issues.append(issue)
            elif edge.expected_kind is DefinitionKind.STRUCTURED_VALUE and target_ref is not None:
                embedding.add(owner, target_ref)
    try:
        _ = embedding.prepare()
    except CycleError:
        issues.append(
            Issue(
                code="cyclic_structured_embedding",
                path=("definitions",),
                message="Break the cycle between embedded structured values.",
            )
        )
    return tuple(issues)


def validate_model_shapes(
    *,
    scope: ModelScope,
    definitions: Sequence[Definition],
    dependencies: Mapping[PinnedDefinitionReference, Definition] | None = None,
) -> tuple[Issue, ...]:
    """Validate the explicitly captured local definitions and exact dependency snapshots."""
    bodies: dict[DefinitionReference, DefinitionBody] = {}
    issues: list[Issue] = []
    local_ids: set[DefinitionId] = set()
    for definition in definitions:
        path = ("definitions", definition.id.value)
        if definition.scope != scope:
            issues.append(
                Issue(
                    code="shape_scope_mismatch",
                    path=path,
                    message="Use a definition in this model scope.",
                )
            )
        elif definition.id in local_ids:
            issues.append(
                Issue(
                    code="duplicate_shape_definition",
                    path=path,
                    message="Supply one inspected revision for each definition.",
                )
            )
        else:
            local_ids.add(definition.id)
            if definition.status is not DefinitionStatus.RETIRED:
                bodies[definition.id] = definition.body
    if dependencies is not None:
        issues.extend(_capture_dependencies(scope=scope, dependencies=dependencies, bodies=bodies))
    return (*issues, *validate_body_graph(bodies=bodies))


def _capture_dependencies(
    *,
    scope: ModelScope,
    dependencies: Mapping[PinnedDefinitionReference, Definition],
    bodies: dict[DefinitionReference, DefinitionBody],
) -> tuple[Issue, ...]:
    issues: list[Issue] = []
    captured: set[tuple[ModelVersion, DefinitionId]] = set()
    for pin, definition in dependencies.items():
        pinned_identity = (pin.model, pin.definition_id)
        if (
            pin.model.scope.project_id != scope.project_id
            or pin.model.scope != definition.scope
            or pin.definition_id != definition.id
            or pin.definition_revision != definition.revision
            or pinned_identity in captured
        ):
            issues.append(
                Issue(
                    code="shape_dependency_mismatch",
                    path=("dependencies", pin.definition_id.value),
                    message="Supply the exact definition revision from the pinned model version.",
                )
            )
        else:
            captured.add(pinned_identity)
            if definition.status is not DefinitionStatus.RETIRED:
                bodies[pin] = definition.body
    return tuple(issues)
