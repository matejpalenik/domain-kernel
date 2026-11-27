"""Validate typed edges and embedding constraints across captured definition bodies."""

from __future__ import annotations

from collections.abc import Mapping
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, final

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.enums.ontology_entity_kind import OntologyEntityKind
from domain_kernel.shared.domain.enums.value_set_membership import ValueSetMembership
from domain_kernel.shared.domain.value_objects.concept_definition import ConceptDefinition
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion
from domain_kernel.shared.domain.value_objects.ontology_term_reference import OntologyTermReference
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.domain.value_objects.scalar_value_type import ScalarValueType
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.domain.value_objects.value_set_definition import ValueSetDefinition
from domain_kernel.shared.domain.value_objects.value_set_type import ValueSetType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.domain.types.definition_body import DefinitionBody
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
    from domain_kernel.shared.domain.value_objects.model_term_reference import ModelTermReference
    from domain_kernel.shared.domain.value_objects.ontology_closure import OntologyClosure
    from domain_kernel.shared.domain.value_objects.shape_reference import ShapeReference

from domain_kernel.shared.domain.policies.shape_ontology_policy import ShapeOntologyPolicy
from domain_kernel.shared.domain.policies.shape_traversal_policy import ShapeTraversalPolicy

type _DependencyIndex = Mapping[tuple[ModelVersion, DefinitionId], PinnedDefinitionReference]


@final
class ShapeGraphValidationPolicy:
    """Check named and pinned references in a model's definition graph."""

    @staticmethod
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
            issues.extend(
                ShapeGraphValidationPolicy._capture_dependencies(
                    scope=scope, dependencies=dependencies, bodies=bodies
                )
            )

        return (
            *issues,
            *ShapeGraphValidationPolicy.validate_body_graph(
                bodies=bodies,
                deferred_scope=scope if defer_pinned_references else None,
                ontologies=ontologies,
            ),
        )

    @staticmethod
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
            for edge in ShapeTraversalPolicy.shape_references(body=body):
                target_ref = ShapeGraphValidationPolicy._qualify_target(
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

                issue = ShapeGraphValidationPolicy._edge_issue(
                    owner=owner, edge=edge, target=target
                )
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
            issues.extend(ShapeOntologyPolicy.ontology_issues(bodies=bodies, resources=ontologies))

        return tuple(issues)

    @staticmethod
    def _definition_term_kind(
        *,
        target: DefinitionBody,
        term: ModelTermReference,
    ) -> OntologyEntityKind | None:
        """Resolve the ontology kind represented by an inspected definition or field."""
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

    @staticmethod
    def _reference_path(
        *, owner: DefinitionReference, edge: ShapeReference
    ) -> tuple[str | int, ...]:
        """Build the diagnostic path for an edge on the owning definition."""
        identifier = (
            owner.definition_id.value
            if isinstance(owner, PinnedDefinitionReference)
            else owner.value
        )

        return ("definitions", identifier, *edge.path)

    @staticmethod
    def _edge_issue(
        *,
        owner: DefinitionReference,
        edge: ShapeReference,
        target: DefinitionBody | None,
    ) -> Issue | None:
        """Check that the resolved target satisfies the edge's expected definition kind."""
        path = ShapeGraphValidationPolicy._reference_path(owner=owner, edge=edge)
        if isinstance(owner, ReferenceDefinitionId) != isinstance(
            edge.target, ReferenceDefinitionId
        ):
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
            and ShapeGraphValidationPolicy._definition_term_kind(target=target, term=edge.term)
            is not edge.term.entity_kind
        ):
            return Issue(
                code="semantic_endpoint_kind",
                path=path,
                message="Choose the mapped entity kind and an exact definition or attribute ID.",
            )

        if edge.closed_vocabulary and isinstance(target, ValueSetDefinition):
            return ShapeGraphValidationPolicy._quantity_set_issue(vocabulary=target, path=path)

        return None

    @staticmethod
    def _quantity_set_issue(
        *, vocabulary: ValueSetDefinition, path: tuple[str | int, ...]
    ) -> Issue | None:
        """Check that units in a quantity value set match the required quantity kind."""
        if vocabulary.membership is not ValueSetMembership.CLOSED:
            return Issue(
                code="quantity_units_not_closed",
                path=path,
                message="Select a closed value set for the quantity unit field.",
            )

        for member in vocabulary.members:
            if member.ontology_term is not None:
                try:
                    OntologyTermReference.require_unit_term(term=member.ontology_term)
                except ValueError:
                    return Issue(
                        code="quantity_unit_term_kind",
                        path=path,
                        message="Use individual or SKOS concept terms for inline quantity units.",
                    )

        return None

    @staticmethod
    def _qualify_target(
        *,
        owner: DefinitionReference,
        target: DefinitionReference,
        dependency_index: _DependencyIndex,
    ) -> DefinitionReference | None:
        """Resolve local dependency edges against the exact pinned definition snapshot."""
        if isinstance(owner, PinnedDefinitionReference) and isinstance(target, DefinitionId):
            return dependency_index.get((owner.model, target))

        return target

    @staticmethod
    def _capture_dependencies(
        *,
        scope: ModelScope,
        dependencies: Mapping[PinnedDefinitionReference, Definition],
        bodies: dict[DefinitionReference, DefinitionBody],
    ) -> tuple[Issue, ...]:
        """Capture exact active dependency bodies and report invalid or repeated pins."""
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
                        message=(
                            "Supply the exact definition revision from the pinned model version."
                        ),
                    )
                )
            else:
                captured.add(pinned_identity)
                if definition.status is not DefinitionStatus.RETIRED:
                    bodies[pin] = definition.body

        return tuple(issues)
