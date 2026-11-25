"""Pure reference traversal and validation for captured business definitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, assert_never

from domain_kernel._shared.domain.acceptance import (
    AcceptanceCheckDefinition,
    DistinctDefinitionsCheck,
    ManualCriterion,
    QuantityRequiredCheck,
)
from domain_kernel._shared.domain.business_decisions import (
    BusinessDecisionDefinition,
    RuleDefinition,
)
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
from domain_kernel._shared.domain.ontology_assets import (
    OntologyEntityKind,
    OntologyTermReference,
    require_unit_term,
)
from domain_kernel._shared.domain.ontology_closure import materialized_terms
from domain_kernel._shared.domain.process_parts import Activity
from domain_kernel._shared.domain.processes import ProcessDefinition
from domain_kernel._shared.domain.semantic_definitions import (
    ModelTermReference,
    OntologyModuleDefinition,
    SemanticLinkDefinition,
)
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.contracts import Issue, PinnedDefinitionReference

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from domain_kernel._shared.domain.data_shapes import AttributeType
    from domain_kernel._shared.domain.definitions import Definition, DefinitionBody
    from domain_kernel._shared.domain.ontology_closure import OntologyClosure
    from domain_kernel._shared.domain.semantic_definitions import SemanticTerm
    from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
    from domain_kernel.shared.contracts import DefinitionReference, ModelScope, ModelVersion


@dataclass(frozen=True, kw_only=True)
class ShapeReference:
    """One typed edge plus its path within the owning body."""

    target: DefinitionReference
    expected_kind: DefinitionKind | None
    path: tuple[str | int, ...]
    closed_vocabulary: bool = False
    embedded: bool = False
    term: ModelTermReference | None = None


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
                    embedded=True,
                )
            )
            return value_type if mapped == target else replace(value_type, structure=mapped)
        case _:
            assert_never(value_type)


def _visit_acceptance(
    *, body: AcceptanceCheckDefinition, visit: _VisitReference
) -> AcceptanceCheckDefinition:
    predicate = body.predicate
    match predicate:
        case DistinctDefinitionsCheck():
            left = visit(
                ShapeReference(
                    target=predicate.left,
                    path=("predicate", "left"),
                    expected_kind=None,
                )
            )
            right = visit(
                ShapeReference(
                    target=predicate.right,
                    path=("predicate", "right"),
                    expected_kind=None,
                )
            )
            return (
                body
                if (left, right) == (predicate.left, predicate.right)
                else replace(
                    body,
                    predicate=replace(predicate, left=left, right=right),
                )
            )
        case QuantityRequiredCheck():
            target = visit(
                ShapeReference(
                    target=predicate.structure,
                    path=("predicate", "structure"),
                    expected_kind=DefinitionKind.STRUCTURED_VALUE,
                )
            )
            return (
                body
                if target == predicate.structure
                else replace(
                    body,
                    predicate=replace(predicate, structure=target),
                )
            )
        case ManualCriterion():
            return body
        case _:
            assert_never(predicate)


def _visit_process(*, body: ProcessDefinition, visit: _VisitReference) -> ProcessDefinition:
    activities: list[Activity] = []
    for index, activity in enumerate(body.activities):
        path = ("activities", index)
        inputs = _visit_sequence(values=activity.input_ids, path=(*path, "input_ids"), visit=visit)
        outputs = _visit_sequence(
            values=activity.output_ids, path=(*path, "output_ids"), visit=visit
        )
        decision = activity.decision_id
        mapped = (
            None
            if decision is None
            else visit(
                ShapeReference(
                    target=decision,
                    path=(*path, "decision_id"),
                    expected_kind=DefinitionKind.BUSINESS_DECISION,
                )
            )
        )
        if (inputs, outputs, mapped) == (activity.input_ids, activity.output_ids, decision):
            activities.append(activity)
        else:
            activities.append(
                Activity.restore(
                    id=activity.id,
                    name=activity.name,
                    display_name=activity.display_name,
                    role_ids=activity.role_ids,
                    input_ids=inputs,
                    output_ids=outputs,
                    decision_id=mapped,
                    evidence=activity.evidence,
                )
            )
    return body if tuple(activities) == body.activities else replace(body, activities=activities)


def _visit_sequence(
    *,
    values: Sequence[DefinitionReference],
    path: tuple[str | int, ...],
    visit: _VisitReference,
) -> tuple[DefinitionReference, ...]:
    return tuple(
        visit(
            ShapeReference(
                target=value,
                path=(*path, index),
                expected_kind=None,
            )
        )
        for index, value in enumerate(values)
    )


def _visit_decision(
    *, body: BusinessDecisionDefinition, visit: _VisitReference
) -> BusinessDecisionDefinition:
    inputs = tuple(
        replace(
            item,
            definition_id=visit(
                ShapeReference(
                    target=item.definition_id,
                    path=("inputs", i, "definition_id"),
                    expected_kind=None,
                )
            ),
        )
        for i, item in enumerate(body.inputs)
    )
    outputs = tuple(
        replace(
            item,
            definition_id=visit(
                ShapeReference(
                    target=item.definition_id,
                    path=("outputs", i, "definition_id"),
                    expected_kind=None,
                )
            ),
        )
        for i, item in enumerate(body.outputs)
    )
    if inputs == body.inputs and outputs == body.outputs:
        return body
    return replace(body, inputs=inputs, outputs=outputs)


def _visit_workflow(
    *,
    body: ProcessDefinition | BusinessDecisionDefinition,
    visit: _VisitReference,
) -> DefinitionBody:
    if isinstance(body, ProcessDefinition):
        return _visit_process(body=body, visit=visit)
    return _visit_decision(body=body, visit=visit)


def _visit_body(  # noqa: PLR0911 - Dispatch each closed body kind to its typed traversal.
    *,
    body: DefinitionBody,
    visit: _VisitReference,
) -> DefinitionBody:
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
            return (
                body
                if (source, target) == (body.source_concept_id, body.target_concept_id)
                else replace(body, source_concept_id=source, target_concept_id=target)
            )
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
        case AcceptanceCheckDefinition():
            return _visit_acceptance(body=body, visit=visit)
        case ProcessDefinition() | BusinessDecisionDefinition():
            return _visit_workflow(body=body, visit=visit)
        case SemanticLinkDefinition():
            return _visit_semantic_link(body=body, visit=visit)
        case RuleDefinition(cardinality=rule) if rule is not None:
            return replace(
                body,
                cardinality=replace(
                    rule,
                    focus=visit(
                        ShapeReference(
                            target=rule.focus,
                            path=("cardinality", "focus"),
                            expected_kind=DefinitionKind.CONCEPT,
                        )
                    ),
                    relationship=visit(
                        ShapeReference(
                            target=rule.relationship,
                            path=("cardinality", "relationship"),
                            expected_kind=DefinitionKind.RELATIONSHIP,
                        )
                    ),
                    applicable_class=visit(
                        ShapeReference(
                            target=rule.applicable_class,
                            path=("cardinality", "applicable_class"),
                            expected_kind=DefinitionKind.CONCEPT,
                        )
                    )
                    if rule.applicable_class is not None
                    else None,
                ),
            )
        case UnitDefinition() | RuleDefinition() | OntologyModuleDefinition():
            return body
        case _:
            assert_never(body)


def _visit_semantic_link(
    *,
    body: SemanticLinkDefinition,
    visit: _VisitReference,
) -> SemanticLinkDefinition:
    def endpoint(*, term: SemanticTerm, label: str) -> SemanticTerm:
        if not isinstance(term, ModelTermReference):
            return term
        identity = visit(
            ShapeReference(
                target=term.definition,
                path=(label, "definition"),
                expected_kind=None,
                term=term,
            )
        )
        return term if identity == term.definition else replace(term, definition=identity)

    subject = endpoint(term=body.subject, label="subject")
    target = endpoint(term=body.object, label="object")
    if (subject, target) == (body.subject, body.object):
        return body
    return replace(body, subject=subject, object=target)


def _definition_term_kind(
    *,
    target: DefinitionBody,
    term: ModelTermReference,
) -> OntologyEntityKind | None:
    if term.local_path:
        if not isinstance(target, (ConceptDefinition, StructuredValueDefinition)):
            return None
        attribute = next(
            (field for field in target.attributes if field.id.value == term.local_path[1]), None
        )
        if attribute is None:
            return None
        if isinstance(attribute.value_type, (ScalarValueType, ValueSetType)):
            return OntologyEntityKind.DATA_PROPERTY
        return OntologyEntityKind.OBJECT_PROPERTY
    return {
        DefinitionKind.CONCEPT: OntologyEntityKind.CLASS,
        DefinitionKind.STRUCTURED_VALUE: OntologyEntityKind.CLASS,
        DefinitionKind.RELATIONSHIP: OntologyEntityKind.OBJECT_PROPERTY,
        DefinitionKind.UNIT: OntologyEntityKind.INDIVIDUAL,
    }.get(target.kind)


def adopted_ontologies(*, bodies: Iterable[DefinitionBody]) -> tuple[OntologyClosure, ...]:
    """Collect reviewed formal modules from the supplied active graph."""
    return tuple(
        dict.fromkeys(
            body.ontology for body in bodies if isinstance(body, OntologyModuleDefinition)
        )
    )


def _ontology_issues(
    *,
    bodies: Mapping[DefinitionReference, DefinitionBody],
    resources: Sequence[OntologyClosure],
) -> tuple[Issue, ...]:
    terms = materialized_terms(closures=(*resources, *adopted_ontologies(bodies=bodies.values())))
    return tuple(
        Issue(
            code="ontology_term_missing",
            path=(
                "definitions",
                owner.definition_id.value
                if isinstance(owner, PinnedDefinitionReference)
                else owner.value,
                "ontology_terms",
                term.term_iri.value,
            ),
            message="Supply the exact term kind in a reviewed module or selected reference pack.",
        )
        for owner, body in bodies.items()
        for term in shape_ontology_terms(body=body)
        if term not in terms
    )


def shape_ontology_terms(*, body: DefinitionBody) -> tuple[OntologyTermReference, ...]:
    """Collect exact term pins without inferring unit or quantity semantics."""
    if isinstance(body, SemanticLinkDefinition):
        return tuple(
            term for term in (body.subject, body.object) if isinstance(term, OntologyTermReference)
        )
    if isinstance(body, UnitDefinition) and body.ontology_term is not None:
        return (body.ontology_term,)
    if isinstance(body, StructuredValueDefinition) and body.quantity is not None:
        kind = body.quantity.quantity_kind
        return () if kind is None else (kind,)
    if isinstance(body, ValueSetDefinition):
        return tuple(
            member.ontology_term for member in body.members if member.ontology_term is not None
        )
    return ()


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
    if edge.expected_kind is not None and target.kind is not edge.expected_kind:
        return Issue(
            code="shape_reference_kind",
            path=path,
            message=f"Use an active {edge.expected_kind.value} definition for this reference.",
        )
    if (
        edge.term is not None
        and _definition_term_kind(target=target, term=edge.term) is not edge.term.entity_kind
    ):
        return Issue(
            code="semantic_endpoint_kind",
            path=path,
            message="Choose the mapped entity kind and an exact definition or attribute ID.",
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
    *,
    bodies: Mapping[DefinitionReference, DefinitionBody],
    deferred_scope: ModelScope | None = None,
    ontologies: Sequence[OntologyClosure] | None = None,
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
            if (
                target is None
                and deferred_scope is not None
                and isinstance(owner, DefinitionId)
                and isinstance(edge.target, PinnedDefinitionReference)
                and edge.target.model.scope.project_id == deferred_scope.project_id
                and edge.target.model.scope != deferred_scope
            ):
                continue
            issue = _edge_issue(owner=owner, edge=edge, target=target)
            if issue is not None:
                issues.append(issue)
            elif edge.embedded and target_ref is not None:
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
    if ontologies is not None:
        issues.extend(_ontology_issues(bodies=bodies, resources=ontologies))
    return tuple(issues)


def validate_model_shapes(
    *,
    scope: ModelScope,
    definitions: Sequence[Definition],
    dependencies: Mapping[PinnedDefinitionReference, Definition] | None = None,
    defer_pinned_references: bool = False,
    ontologies: Sequence[OntologyClosure] | None = None,
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
    return (
        *issues,
        *validate_body_graph(
            bodies=bodies,
            deferred_scope=scope if defer_pinned_references else None,
            ontologies=ontologies,
        ),
    )


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
