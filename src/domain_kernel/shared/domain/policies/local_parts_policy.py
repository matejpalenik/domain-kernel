"""Rewrite owner-local part identities and keep their internal references closed."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from itertools import count
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel.shared.domain.codecs.record_restoration import RecordRestoration
from domain_kernel.shared.domain.policies.shape_traversal_policy import ShapeTraversalPolicy
from domain_kernel.shared.domain.types.definition_reference import DefinitionReference
from domain_kernel.shared.domain.value_objects.business_decision_definition import (
    BusinessDecisionDefinition,
)
from domain_kernel.shared.domain.value_objects.concept_definition import ConceptDefinition
from domain_kernel.shared.domain.value_objects.model_term_reference import ModelTermReference
from domain_kernel.shared.domain.value_objects.process_definition import ProcessDefinition
from domain_kernel.shared.domain.value_objects.semantic_link_definition import (
    SemanticLinkDefinition,
)
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from domain_kernel.shared.domain.types.definition_body import DefinitionBody
    from domain_kernel.shared.domain.types.process_node_id import ProcessNodeId
    from domain_kernel.shared.domain.types.semantic_term import SemanticTerm


@final
class LocalPartsPolicy:
    """Copy and normalize identities local to authored shapes."""

    @staticmethod
    def copy_local_parts(*, body: DefinitionBody) -> DefinitionBody:
        """Remint owner-local parts and keep all local references to those parts."""
        return LocalPartsPolicy._with_parts(body=body, next_id=lambda: uuid4().hex)

    @staticmethod
    def normalize_local_parts(*, body: DefinitionBody) -> DefinitionBody:
        """Compare deterministic structure after removing newly minted child identities."""
        positions = count()
        return LocalPartsPolicy._with_parts(body=body, next_id=lambda: f"part-{next(positions)}")

    @staticmethod
    def copy_shape_bodies[RefT: DefinitionReference](
        *,
        bodies: Mapping[RefT, DefinitionBody],
        replacements: Mapping[DefinitionReference, DefinitionReference],
        existing: Mapping[RefT, DefinitionBody] | None = None,
    ) -> dict[RefT, DefinitionBody]:
        """Remint local parts and rewrite all links to the copied owner-qualified fields."""
        supplied: Mapping[RefT, DefinitionBody] = {} if existing is None else existing
        captured = {
            key: LocalPartsPolicy.copy_local_parts(body=body)
            for key, body in bodies.items()
            if key not in supplied
        }

        return LocalPartsPolicy._rewrite_shape_bodies(
            original=bodies,
            rewritten={**supplied, **captured},
            captured=captured,
            replacements=replacements,
        )

    @staticmethod
    def comparable_shape_bodies[RefT: DefinitionReference](
        *,
        bodies: Mapping[RefT, DefinitionBody],
        replacements: Mapping[DefinitionReference, DefinitionReference],
    ) -> dict[RefT, DefinitionBody]:
        """Normalize linked local parts while comparing two exact model scopes."""
        normalized = {
            key: LocalPartsPolicy.normalize_local_parts(body=body) for key, body in bodies.items()
        }

        return LocalPartsPolicy._rewrite_shape_bodies(
            original=bodies,
            rewritten=normalized,
            captured=normalized,
            replacements=replacements,
        )

    @staticmethod
    def _part[T](*, value: T, next_id: Callable[[], str], **edges: object) -> T:
        """Copy a local part with a replacement identity and any rewritten links."""
        if not is_dataclass(value):
            raise TypeError("Use a declared local part record")

        attributes: dict[str, object] = {
            field.name: getattr(value, field.name) for field in fields(value)
        }
        identifier = attributes.get("id")
        if not isinstance(identifier, OpaqueIdentifier):
            raise TypeError("Use a nominal local part identity")

        attributes.update(edges)
        attributes["id"] = type(identifier)(value=next_id())

        record = type(value)
        copied = RecordRestoration.construct_record(record=record, attributes=attributes)
        if not isinstance(copied, record):
            raise TypeError("Restore the declared local part record")

        return copied

    @staticmethod
    def _process(*, body: ProcessDefinition, next_id: Callable[[], str]) -> ProcessDefinition:
        """Rewrite all process-local identities and the edges that refer to them."""
        roles = {
            item.id: LocalPartsPolicy._part(value=item, next_id=next_id) for item in body.roles
        }
        conditions = {
            item.id: LocalPartsPolicy._part(value=item, next_id=next_id) for item in body.conditions
        }

        activities = {
            item.id: LocalPartsPolicy._part(
                value=item,
                next_id=next_id,
                role_ids=tuple(roles[identity].id for identity in item.role_ids),
            )
            for item in body.activities
        }
        events = {
            item.id: LocalPartsPolicy._part(value=item, next_id=next_id) for item in body.events
        }
        gateways = {
            item.id: LocalPartsPolicy._part(value=item, next_id=next_id) for item in body.gateways
        }

        nodes: dict[ProcessNodeId, ProcessNodeId] = {
            **{before: after.id for before, after in activities.items()},
            **{before: after.id for before, after in events.items()},
            **{before: after.id for before, after in gateways.items()},
        }

        return replace(
            body,
            roles=tuple(roles.values()),
            activities=tuple(activities.values()),
            events=tuple(events.values()),
            gateways=tuple(gateways.values()),
            conditions=tuple(conditions.values()),
            flows=tuple(
                LocalPartsPolicy._part(
                    value=item,
                    next_id=next_id,
                    source_id=nodes[item.source_id],
                    target_id=nodes[item.target_id],
                    condition_id=None
                    if item.condition_id is None
                    else conditions[item.condition_id].id,
                )
                for item in body.flows
            ),
        )

    @staticmethod
    def _decision(
        *,
        body: BusinessDecisionDefinition,
        next_id: Callable[[], str],
    ) -> BusinessDecisionDefinition:
        """Rewrite decision-local identities and the rules that pin their outputs."""
        conditions = {
            item.id: LocalPartsPolicy._part(value=item, next_id=next_id) for item in body.conditions
        }

        return replace(
            body,
            conditions=tuple(conditions.values()),
            rules=tuple(
                replace(
                    item,
                    condition_ids=tuple(conditions[identity].id for identity in item.condition_ids),
                )
                for item in body.rules
            ),
        )

    @staticmethod
    def _fields(
        *,
        body: ConceptDefinition | StructuredValueDefinition,
        next_id: Callable[[], str],
    ) -> DefinitionBody:
        """Rewrite local attribute and key identities together with their links."""
        attributes = {
            item.id: LocalPartsPolicy._part(value=item, next_id=next_id) for item in body.attributes
        }
        copied = tuple(attributes.values())

        if isinstance(body, ConceptDefinition):
            return replace(
                body,
                attributes=copied,
                keys=tuple(
                    LocalPartsPolicy._part(
                        value=item,
                        next_id=next_id,
                        attributes=tuple(attributes[identity].id for identity in item.attributes),
                    )
                    for item in body.keys
                ),
            )

        quantity = body.quantity
        if quantity is not None:
            quantity = replace(
                quantity,
                magnitude=attributes[quantity.magnitude].id,
                unit=attributes[quantity.unit].id,
            )

        return replace(body, attributes=copied, quantity=quantity)

    @staticmethod
    def _with_parts(*, body: DefinitionBody, next_id: Callable[[], str]) -> DefinitionBody:
        """Apply the identity policy to the body type that owns the local parts."""
        if isinstance(body, (ConceptDefinition, StructuredValueDefinition)):
            return LocalPartsPolicy._fields(body=body, next_id=next_id)
        if isinstance(body, ProcessDefinition):
            return LocalPartsPolicy._process(body=body, next_id=next_id)
        if isinstance(body, BusinessDecisionDefinition):
            return LocalPartsPolicy._decision(body=body, next_id=next_id)

        return body

    @staticmethod
    def _rewrite_shape_bodies[RefT: DefinitionReference](
        *,
        original: Mapping[RefT, DefinitionBody],
        rewritten: Mapping[RefT, DefinitionBody],
        captured: Mapping[RefT, DefinitionBody],
        replacements: Mapping[DefinitionReference, DefinitionReference],
    ) -> dict[RefT, DefinitionBody]:
        """Remap definition and field references throughout the captured shape bodies."""
        attributes: dict[tuple[DefinitionReference, str], str] = {}

        for key, before in original.items():
            after = rewritten[key]
            if isinstance(before, (ConceptDefinition, StructuredValueDefinition)) and isinstance(
                after, (ConceptDefinition, StructuredValueDefinition)
            ):
                by_name = {field.name: field.id.value for field in after.attributes}
                for field in before.attributes:
                    if field.name in by_name:
                        attributes[(key, field.id.value)] = by_name[field.name]

        def endpoint(*, term: SemanticTerm) -> SemanticTerm:
            """Resolve an endpoint to the matching field identity in the rewritten graph."""
            if not isinstance(term, ModelTermReference) or not term.local_path:
                return term

            field = term.local_path[1]
            replacement = attributes.get((term.definition, field), field)
            return replace(term, local_path=("attributes", replacement))

        return {
            key: ShapeTraversalPolicy.remap_shape(
                body=replace(
                    body, subject=endpoint(term=body.subject), object=endpoint(term=body.object)
                )
                if isinstance(body, SemanticLinkDefinition)
                else body,
                replacements=replacements,
            )
            for key, body in captured.items()
        }
