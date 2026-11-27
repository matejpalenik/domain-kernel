"""Collect and remap typed references in authored definition bodies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, assert_never, final

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.entities.activity import Activity
from domain_kernel.shared.domain.types.definition_reference import DefinitionReference
from domain_kernel.shared.domain.value_objects.acceptance_check_definition import (
    AcceptanceCheckDefinition,
)
from domain_kernel.shared.domain.value_objects.business_decision_definition import (
    BusinessDecisionDefinition,
)
from domain_kernel.shared.domain.value_objects.concept_definition import ConceptDefinition
from domain_kernel.shared.domain.value_objects.concept_reference_type import ConceptReferenceType
from domain_kernel.shared.domain.value_objects.distinct_definitions_check import (
    DistinctDefinitionsCheck,
)
from domain_kernel.shared.domain.value_objects.manual_criterion import ManualCriterion
from domain_kernel.shared.domain.value_objects.model_term_reference import ModelTermReference
from domain_kernel.shared.domain.value_objects.ontology_module_definition import (
    OntologyModuleDefinition,
)
from domain_kernel.shared.domain.value_objects.process_definition import ProcessDefinition
from domain_kernel.shared.domain.value_objects.quantity_required_check import QuantityRequiredCheck
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition
from domain_kernel.shared.domain.value_objects.rule_definition import RuleDefinition
from domain_kernel.shared.domain.value_objects.scalar_value_type import ScalarValueType
from domain_kernel.shared.domain.value_objects.semantic_link_definition import (
    SemanticLinkDefinition,
)
from domain_kernel.shared.domain.value_objects.shape_reference import ShapeReference
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.domain.value_objects.structured_value_type import StructuredValueType
from domain_kernel.shared.domain.value_objects.unit_definition import UnitDefinition
from domain_kernel.shared.domain.value_objects.value_set_definition import ValueSetDefinition
from domain_kernel.shared.domain.value_objects.value_set_type import ValueSetType

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
    from domain_kernel.shared.domain.types.attribute_type import AttributeType
    from domain_kernel.shared.domain.types.definition_body import DefinitionBody
    from domain_kernel.shared.domain.types.semantic_term import SemanticTerm


type _VisitReference = Callable[[ShapeReference], DefinitionReference]


@final
class ShapeTraversalPolicy:
    """Inspect and remap references in authored definition bodies."""

    @staticmethod
    def shape_references(*, body: DefinitionBody) -> tuple[ShapeReference, ...]:
        """List the definition edges in one body, in record order."""
        edges: list[ShapeReference] = []

        def collect(edge: ShapeReference) -> DefinitionReference:
            """Record one edge and keep its existing target."""
            edges.append(edge)
            return edge.target

        _ = ShapeTraversalPolicy._visit_body(body=body, visit=collect)

        return tuple(edges)

    @staticmethod
    def remap_shape(
        *,
        body: DefinitionBody,
        replacements: Mapping[DefinitionReference, DefinitionReference],
    ) -> DefinitionBody:
        """Replace exact definition references while retaining local child identities."""
        return ShapeTraversalPolicy._visit_body(
            body=body, visit=lambda edge: replacements.get(edge.target, edge.target)
        )

    @staticmethod
    def _visit_attribute_type(
        *,
        value_type: AttributeType,
        path: tuple[str | int, ...],
        closed_vocabulary: bool,
        visit: _VisitReference,
    ) -> AttributeType:
        """Visit the definition references used by a field's declared shape."""
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

    @staticmethod
    def _visit_acceptance(
        *, body: AcceptanceCheckDefinition, visit: _VisitReference
    ) -> AcceptanceCheckDefinition:
        """Visit the definition references captured by an acceptance check."""
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

    @staticmethod
    def _visit_process(*, body: ProcessDefinition, visit: _VisitReference) -> ProcessDefinition:
        """Visit an activity's references while retaining its process-local identities."""
        activities: list[Activity] = []

        for index, activity in enumerate(body.activities):
            path = ("activities", index)
            inputs = ShapeTraversalPolicy._visit_sequence(
                values=activity.input_ids, path=(*path, "input_ids"), visit=visit
            )
            outputs = ShapeTraversalPolicy._visit_sequence(
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

        return (
            body if tuple(activities) == body.activities else replace(body, activities=activities)
        )

    @staticmethod
    def _visit_sequence(
        *,
        values: Sequence[DefinitionReference],
        path: tuple[str | int, ...],
        visit: _VisitReference,
    ) -> tuple[DefinitionReference, ...]:
        """Visit a sequence and reuse it when its elements are unchanged."""
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

    @staticmethod
    def _visit_decision(
        *, body: BusinessDecisionDefinition, visit: _VisitReference
    ) -> BusinessDecisionDefinition:
        """Visit references in the declared input and output types of a decision."""
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

    @staticmethod
    def _visit_workflow(
        *,
        body: ProcessDefinition | BusinessDecisionDefinition,
        visit: _VisitReference,
    ) -> DefinitionBody:
        """Dispatch reference traversal for a process or business decision body."""
        if isinstance(body, ProcessDefinition):
            return ShapeTraversalPolicy._visit_process(body=body, visit=visit)

        return ShapeTraversalPolicy._visit_decision(body=body, visit=visit)

    @staticmethod
    def _visit_body(  # noqa: PLR0911 - Dispatch each closed body kind to its typed traversal.
        *,
        body: DefinitionBody,
        visit: _VisitReference,
    ) -> DefinitionBody:
        """Visit the typed references for the supplied authored definition body."""
        match body:
            case ConceptDefinition() | StructuredValueDefinition():
                unit_field: AttributeId | None = None
                if isinstance(body, StructuredValueDefinition) and body.quantity is not None:
                    unit_field = body.quantity.unit

                attributes = tuple(
                    attribute.with_value_type(
                        value_type=ShapeTraversalPolicy._visit_attribute_type(
                            value_type=attribute.value_type,
                            path=("attributes", index, "value_type"),
                            closed_vocabulary=attribute.id == unit_field,
                            visit=visit,
                        ),
                    )
                    for index, attribute in enumerate(body.attributes)
                )

                return (
                    body if attributes == body.attributes else replace(body, attributes=attributes)
                )
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
                return ShapeTraversalPolicy._visit_acceptance(body=body, visit=visit)
            case ProcessDefinition() | BusinessDecisionDefinition():
                return ShapeTraversalPolicy._visit_workflow(body=body, visit=visit)
            case SemanticLinkDefinition():
                return ShapeTraversalPolicy._visit_semantic_link(body=body, visit=visit)
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

    @staticmethod
    def _visit_semantic_link(
        *,
        body: SemanticLinkDefinition,
        visit: _VisitReference,
    ) -> SemanticLinkDefinition:
        """Visit each model-backed endpoint of the descriptive semantic link."""

        def endpoint(*, term: SemanticTerm, label: str) -> SemanticTerm:
            """Visit a model definition endpoint or preserve its exact ontology term."""
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
