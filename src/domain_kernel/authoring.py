"""Build connected model change plans with an in-memory authoring session."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Final, Never, final
from uuid import uuid4

from domain_kernel._shared.domain.authoring import (
    AuthoredContent,
    CreateDefinition,
    IncludeCase,
    ModelChangePlan,
    RestoreDefinition,
    RetireDefinition,
    ReviseDefinition,
)
from domain_kernel._shared.domain.data_shapes import (
    AttributeDefinition,
    KeyDefinition,
    QuantityBinding,
)
from domain_kernel._shared.domain.definitions import (
    Concept,
    ConceptDefinition,
    Definition,
    RelationshipDefinition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
)
from domain_kernel._shared.domain.dependency_requests import DependencyChangeRequest
from domain_kernel._shared.domain.model_values import Terminology
from domain_kernel._shared.domain.naming import resolve_names
from domain_kernel._shared.domain.processes import ProcessDefinition
from domain_kernel._shared.domain.shape_graph import validate_model_shapes
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.definition_errors import DefinitionAlreadyExistsError
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.models import ModelInfo
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.shared.validation import is_non_string_sequence, require_exact, require_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.authoring import LifecycleOperation, PlannedOperation
    from domain_kernel._shared.domain.data_shapes import AttributeType, ConstraintDefinition
    from domain_kernel._shared.domain.definitions import DefinitionBody, ValueSetMember
    from domain_kernel._shared.domain.model_values import (
        CollectionKind,
        Nullability,
        RelationshipCardinality,
        ValueSetMembership,
    )
    from domain_kernel._shared.domain.ontology_assets import OntologyTermReference
    from domain_kernel._shared.domain.process_parts import (
        Activity,
        Condition,
        Event,
        Flow,
        Gateway,
        Role,
    )
    from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
    from domain_kernel.modeling.domain.identifiers.key_id import KeyId
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.models import ReviewCase
    from domain_kernel.shared.contracts import (
        CompanyDefinitionReference,
        Count,
        DefinitionReference,
    )


_OWNED_ISSUE_PATH_LENGTH = 2


class Unset(Enum):
    """Omission marker for authoring fields that preserve an inspected value."""

    VALUE = "unset"


UNSET: Final = Unset.VALUE


def _selected[T](*, value: T | Unset, existing: T) -> T:
    return existing if isinstance(value, Unset) else value


@dataclass(frozen=True, kw_only=True)
class _ConceptChildren:
    original: Concept
    attributes: tuple[AttributeDefinition, ...]
    keys: tuple[KeyDefinition, ...]
    changed_attributes: frozenset[AttributeId] = frozenset()
    changed_keys: frozenset[KeyId] = frozenset()


@final
class DomainModelBuilder:
    """Capture authored definitions and inspected references before submission."""

    def __init__(self, *, model_info: ModelInfo) -> None:
        """Pin the inspected workspace revision without obtaining resources."""
        require_exact(value=model_info, expected=ModelInfo, field="Model information")
        self._info = model_info
        self._operations: list[PlannedOperation] = []
        self._bindings: dict[DefinitionId, Definition] = {}
        self._last_plan: ModelChangePlan | None = None
        self._dependency_change: DependencyChangeRequest | None = None
        self._local_creations: set[DefinitionId] = set()
        self._local_revisions: set[DefinitionId] = set()
        self._children: dict[DefinitionId, _ConceptChildren] = {}
        self._explicit_bodies: set[DefinitionId] = set()
        self._edited_fields: dict[DefinitionId, frozenset[str]] = {}

    def add_definition(  # noqa: PLR0913 - The authoring fields are explicit.
        self,
        *,
        meaning: str,
        body: DefinitionBody,
        display_name: str | None = None,
        name: str | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Never] = (),
        referenced_definitions: Sequence[Definition] = (),
    ) -> DefinitionId:
        """Author one typed definition and capture its inspected references."""
        if not is_non_string_sequence(evidence) or evidence:
            raise ValueError("Source evidence requires a captured source revision")
        if not is_non_string_sequence(referenced_definitions):
            raise TypeError("Referenced definitions must be a sequence")
        lookup, label = resolve_names(name=name, display_name=display_name)
        captured = _process_bindings(body=body)
        bindings = self._with_bindings(definitions=(*referenced_definitions, *captured))
        names = {
            item.content.name for item in self._operations if isinstance(item, CreateDefinition)
        }
        if lookup in names or lookup in {binding.name for binding in bindings.values()}:
            raise DefinitionAlreadyExistsError
        identity = DefinitionId(value=uuid4().hex)
        operation = CreateDefinition(
            definition_id=identity,
            content=AuthoredContent(
                name=lookup,
                display_name=label,
                meaning=meaning,
                body=body,
                aliases=aliases,
                terminology=Terminology() if terminology is None else terminology,
            ),
            reason="Create definition",
        )
        _ = operation.draft(scope=self._info.scope)
        self._operations.append(operation)
        self._local_creations.add(identity)
        self._bindings = bindings
        return identity

    def _with_bindings(
        self, *, definitions: Sequence[Definition]
    ) -> dict[DefinitionId, Definition]:
        if not is_non_string_sequence(definitions):
            raise TypeError("Referenced definitions must be a sequence")
        bindings = self._bindings.copy()
        for supplied in definitions:
            bound = _capture(definition=supplied)
            if bound.scope != self._info.scope or bound.status is not DefinitionStatus.APPROVED:
                raise ValueError("Supply approved definitions inspected in this model")
            if bindings.setdefault(bound.id, bound) != bound:
                raise ValueError("Bind only one inspected revision of an existing definition")
        return bindings

    def add_concept(  # noqa: PLR0913 - Keep the concept fields explicit.
        self,
        *,
        meaning: str,
        display_name: str | None = None,
        name: str | None = None,
        attributes: Sequence[AttributeDefinition] = (),
        keys: Sequence[KeyDefinition] = (),
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Never] = (),
        referenced_definitions: Sequence[Definition] = (),
    ) -> DefinitionId:
        """Author a concept and its direct business fields and keys."""
        return self.add_definition(
            meaning=meaning,
            display_name=display_name,
            name=name,
            body=ConceptDefinition(attributes=attributes, keys=keys),
            aliases=aliases,
            terminology=terminology,
            evidence=evidence,
            referenced_definitions=referenced_definitions,
        )

    def add_process(  # noqa: PLR0913 - Explicit named process parts.
        self,
        *,
        meaning: str,
        activities: Sequence[Activity],
        events: Sequence[Event],
        roles: Sequence[Role],
        flows: Sequence[Flow],
        display_name: str | None = None,
        name: str | None = None,
        gateways: Sequence[Gateway] = (),
        conditions: Sequence[Condition] = (),
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Never] = (),
        referenced_definitions: Sequence[Definition] = (),
    ) -> DefinitionId:
        """Author one complete descriptive process and bind its inspected definitions."""
        return self.add_definition(
            body=ProcessDefinition(
                activities=activities,
                events=events,
                roles=roles,
                flows=flows,
                gateways=gateways,
                conditions=conditions,
            ),
            meaning=meaning,
            display_name=display_name,
            name=name,
            aliases=aliases,
            terminology=terminology,
            evidence=evidence,
            referenced_definitions=referenced_definitions,
        )

    def add_unit(  # noqa: PLR0913 - The authoring fields are explicit.
        self,
        *,
        meaning: str,
        display_name: str | None = None,
        name: str | None = None,
        symbol: str | None = None,
        ontology_term: OntologyTermReference | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Never] = (),
    ) -> DefinitionId:
        """Author one reusable unit under the ordinary definition contract."""
        return self.add_definition(
            meaning=meaning,
            display_name=display_name,
            name=name,
            aliases=aliases,
            terminology=terminology,
            evidence=evidence,
            body=UnitDefinition(
                symbol=symbol,
                ontology_term=ontology_term,
            ),
        )

    def add_value_set(  # noqa: PLR0913 - The authoring fields are explicit.
        self,
        *,
        meaning: str,
        membership: ValueSetMembership,
        members: Sequence[ValueSetMember],
        display_name: str | None = None,
        name: str | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Never] = (),
        referenced_definitions: Sequence[Definition] = (),
    ) -> DefinitionId:
        """Author the exact vocabulary and its typed unit edges."""
        return self.add_definition(
            meaning=meaning,
            display_name=display_name,
            name=name,
            aliases=aliases,
            terminology=terminology,
            evidence=evidence,
            referenced_definitions=referenced_definitions,
            body=ValueSetDefinition(membership=membership, members=members),
        )

    def add_quantity(  # noqa: PLR0913 - The authoring fields are explicit.
        self,
        *,
        meaning: str,
        units: Definition[ValueSetDefinition] | DefinitionReference,
        quantity_kind: OntologyTermReference | None = None,
        display_name: str | None = None,
        name: str | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Never] = (),
    ) -> DefinitionId:
        """Author one local quantity using an explicitly bound unit vocabulary."""
        ref, binding = _reference(value=units, kind=DefinitionKind.VALUE_SET)
        magnitude = AttributeDefinition.decimal(display_name="Magnitude", required=True)
        unit = AttributeDefinition.value_set(display_name="Unit", value_set=ref, required=True)
        return self.add_definition(
            meaning=meaning,
            display_name=display_name,
            name=name,
            aliases=aliases,
            terminology=terminology,
            evidence=evidence,
            referenced_definitions=binding,
            body=StructuredValueDefinition(
                attributes=(magnitude, unit),
                quantity=QuantityBinding(
                    magnitude=magnitude.id,
                    unit=unit.id,
                    quantity_kind=quantity_kind,
                ),
            ),
        )

    def add_relationship(  # noqa: PLR0913 - The authoring fields are explicit.
        self,
        *,
        meaning: str,
        source: Definition[ConceptDefinition] | CompanyDefinitionReference,
        target: Definition[ConceptDefinition] | CompanyDefinitionReference,
        cardinality: RelationshipCardinality,
        display_name: str | None = None,
        name: str | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Never] = (),
    ) -> DefinitionId:
        """Author a directed business relationship between exact concept references."""
        from_id, from_binding = _reference(value=source, kind=DefinitionKind.CONCEPT)
        to_id, to_binding = _reference(value=target, kind=DefinitionKind.CONCEPT)
        return self.add_definition(
            meaning=meaning,
            display_name=display_name,
            name=name,
            aliases=aliases,
            terminology=terminology,
            evidence=evidence,
            referenced_definitions=(
                *from_binding,
                *to_binding,
            ),
            body=RelationshipDefinition(
                source_concept_id=from_id,
                target_concept_id=to_id,
                cardinality=cardinality,
            ),
        )

    def edit_definition(  # noqa: PLR0913 - Each field may be preserved independently.
        self,
        *,
        definition: Definition,
        display_name: str | Unset = UNSET,
        meaning: str | Unset = UNSET,
        body: DefinitionBody | Unset = UNSET,
        aliases: Sequence[str] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        evidence: Sequence[Never] | Unset = UNSET,
        referenced_definitions: Sequence[Definition] = (),
    ) -> None:
        """Stage an inspected revision with stable identity and preserved omissions."""
        if not isinstance(evidence, Unset) and (not is_non_string_sequence(evidence) or evidence):
            raise ValueError("Source evidence requires a captured source revision")
        before = _capture(definition=definition)
        if before.id in self._children and not isinstance(body, Unset):
            raise ValueError("A whole-body edit conflicts with staged child edits")
        fields = frozenset(
            name
            for name, value in (
                ("display_name", display_name),
                ("meaning", meaning),
                ("body", body),
                ("aliases", aliases),
                ("terminology", terminology),
            )
            if not isinstance(value, Unset)
        )
        previous = self._edited_fields.get(before.id, frozenset())
        if not fields or previous & fields:
            raise ValueError("Edit distinct authored fields from the original inspected definition")
        current = self._capture_lifecycle(before=before)
        if current is None:
            content = AuthoredContent(
                name=before.name,
                display_name=before.display_name,
                meaning=before.meaning,
                body=before.body,
                aliases=before.aliases,
                terminology=before.terminology,
                schema_origins=before.schema_origins,
            )
        elif (
            isinstance(current, ReviseDefinition)
            and before.id in self._local_revisions
            and current.before == before
        ):
            content = current.content
        else:
            raise ValueError("Inspect the same definition before staging another edit")
        revised = replace(
            content,
            display_name=_selected(value=display_name, existing=content.display_name),
            meaning=_selected(value=meaning, existing=content.meaning),
            body=_selected(value=body, existing=content.body),
            aliases=_selected(value=aliases, existing=content.aliases),
            terminology=_selected(value=terminology, existing=content.terminology),
        )
        if revised == content:
            raise ValueError("Change the inspected definition before staging an edit")
        updated = ReviseDefinition(before=before, reason="Revise definition", content=revised)
        _ = updated.draft()
        if not is_non_string_sequence(referenced_definitions):
            raise TypeError("Referenced definitions must be a sequence")
        captured = _process_bindings(body=revised.body)
        bindings = self._with_bindings(definitions=(*referenced_definitions, *captured))
        if current is None:
            self._operations.append(updated)
        else:
            self._operations[self._operations.index(current)] = updated
        self._edited_fields[before.id] = previous | fields
        self._local_revisions.add(before.id)
        if not isinstance(body, Unset):
            self._explicit_bodies.add(before.id)
        self._bindings = bindings

    def _capture_lifecycle(self, *, before: Definition) -> LifecycleOperation | None:
        if before.scope != self._info.scope:
            raise ValueError("Inspect the definition in this model before editing")
        return next(
            (
                operation
                for operation in self._operations
                if isinstance(operation, (ReviseDefinition, RetireDefinition, RestoreDefinition))
                and operation.before.id == before.id
            ),
            None,
        )

    def edit_concept(  # noqa: PLR0913 - Each field may be preserved independently.
        self,
        *,
        concept: Concept,
        display_name: str | Unset = UNSET,
        meaning: str | Unset = UNSET,
        attributes: Sequence[AttributeDefinition] | Unset = UNSET,
        keys: Sequence[KeyDefinition] | Unset = UNSET,
        aliases: Sequence[str] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        evidence: Sequence[Never] | Unset = UNSET,
        referenced_definitions: Sequence[Definition] = (),
    ) -> None:
        """Stage a concept's drafted meaning and optional replacement collections."""
        require_exact(value=concept, expected=Concept, field="Inspected concept")
        body = (
            UNSET
            if isinstance(attributes, Unset) and isinstance(keys, Unset)
            else ConceptDefinition(
                attributes=_selected(value=attributes, existing=concept.attributes),
                keys=_selected(value=keys, existing=concept.keys),
            )
        )
        self.edit_definition(
            definition=concept,
            display_name=display_name,
            meaning=meaning,
            body=body,
            aliases=aliases,
            terminology=terminology,
            evidence=evidence,
            referenced_definitions=referenced_definitions,
        )

    def edit_relationship(  # noqa: PLR0913 - Each field may be preserved independently.
        self,
        *,
        relationship: Definition[RelationshipDefinition],
        display_name: str | Unset = UNSET,
        meaning: str | Unset = UNSET,
        source: Definition[ConceptDefinition] | CompanyDefinitionReference | Unset = UNSET,
        target: Definition[ConceptDefinition] | CompanyDefinitionReference | Unset = UNSET,
        cardinality: RelationshipCardinality | Unset = UNSET,
        aliases: Sequence[str] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        evidence: Sequence[Never] | Unset = UNSET,
    ) -> None:
        """Stage an inspected relationship's directed endpoints and meaning."""
        require_exact(
            value=relationship.body, expected=RelationshipDefinition, field="Relationship"
        )
        from_value = _selected(value=source, existing=relationship.body.source_concept_id)
        to_value = _selected(value=target, existing=relationship.body.target_concept_id)
        from_id, from_binding = _reference(value=from_value, kind=DefinitionKind.CONCEPT)
        to_id, to_binding = _reference(value=to_value, kind=DefinitionKind.CONCEPT)
        self.edit_definition(
            definition=relationship,
            display_name=display_name,
            meaning=meaning,
            aliases=aliases,
            terminology=terminology,
            evidence=evidence,
            referenced_definitions=(*from_binding, *to_binding),
            body=RelationshipDefinition(
                source_concept_id=from_id,
                target_concept_id=to_id,
                cardinality=_selected(value=cardinality, existing=relationship.body.cardinality),
            ),
        )

    def edit_unit(  # noqa: PLR0913 - Each field may be preserved independently.
        self,
        *,
        unit: Definition[UnitDefinition],
        display_name: str | Unset = UNSET,
        meaning: str | Unset = UNSET,
        symbol: str | Unset | None = UNSET,
        ontology_term: OntologyTermReference | Unset | None = UNSET,
        aliases: Sequence[str] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        evidence: Sequence[Never] | Unset = UNSET,
    ) -> None:
        """Stage unit metadata, including a deliberate clearing of an optional term or symbol."""
        require_exact(value=unit.body, expected=UnitDefinition, field="Unit")
        self.edit_definition(
            definition=unit,
            display_name=display_name,
            meaning=meaning,
            aliases=aliases,
            terminology=terminology,
            evidence=evidence,
            body=UnitDefinition(
                symbol=_selected(value=symbol, existing=unit.body.symbol),
                ontology_term=_selected(value=ontology_term, existing=unit.body.ontology_term),
            ),
        )

    def remove_definition(
        self,
        *,
        definition: Definition,
        replacements: Sequence[Definition | DefinitionId] = (),
    ) -> None:
        """Stage a retirement with explicit replacement identities."""
        before = _capture(definition=definition)
        if before.id in self._children or self._capture_lifecycle(before=before) is not None:
            raise ValueError("Remove or edit an identity only once within the plan")
        if not is_non_string_sequence(replacements):
            raise TypeError("Replacements must be a sequence")
        bound: list[Definition] = []
        identities: list[DefinitionId] = []
        for value in replacements:
            if isinstance(value, Definition):
                if value.kind is not before.kind:
                    raise ValueError("Choose replacements of the same definition kind")
                bound.append(value)
                identities.append(value.id)
            else:
                require_exact(value=value, expected=DefinitionId, field="Replacement ID")
                identities.append(value)
        bindings = self._with_bindings(definitions=bound)
        self._operations.append(
            RetireDefinition(
                before=before,
                replacement_ids=identities,
                reason="Retire definition",
            )
        )
        self._local_revisions.add(before.id)
        self._bindings = bindings

    def restore_definition(self, *, definition: Definition) -> None:
        """Stage restoration of the same retired identity and meaning."""
        before = _capture(definition=definition)
        if before.id in self._children or self._capture_lifecycle(before=before) is not None:
            raise ValueError("Restore or edit an identity only once within the plan")
        self._operations.append(RestoreDefinition(before=before, reason="Restore definition"))
        self._local_revisions.add(before.id)

    def remove_concept(
        self,
        *,
        concept: Concept,
        replacements: Sequence[Definition[ConceptDefinition] | DefinitionId] = (),
    ) -> None:
        """Stage reviewed retirement of an inspected concept."""
        require_exact(value=concept, expected=Concept, field="Inspected concept")
        self.remove_definition(definition=concept, replacements=replacements)

    def remove_relationship(
        self,
        *,
        relationship: Definition[RelationshipDefinition],
        replacements: Sequence[Definition[RelationshipDefinition] | DefinitionId] = (),
    ) -> None:
        """Stage reviewed retirement of an inspected relationship."""
        require_exact(
            value=relationship.body, expected=RelationshipDefinition, field="Relationship"
        )
        self.remove_definition(definition=relationship, replacements=replacements)

    def remove_unit(
        self,
        *,
        unit: Definition[UnitDefinition],
        replacements: Sequence[Definition[UnitDefinition] | DefinitionId] = (),
    ) -> None:
        """Stage reviewed retirement of a unit and explicit replacement lineage."""
        require_exact(value=unit.body, expected=UnitDefinition, field="Unit")
        self.remove_definition(definition=unit, replacements=replacements)

    def restore_concept(self, *, concept: Concept) -> None:
        """Stage restoration of a retired concept."""
        require_exact(value=concept, expected=Concept, field="Inspected concept")
        self.restore_definition(definition=concept)

    def restore_relationship(self, *, relationship: Definition[RelationshipDefinition]) -> None:
        """Stage restoration of a retired relationship."""
        require_exact(
            value=relationship.body, expected=RelationshipDefinition, field="Relationship"
        )
        self.restore_definition(definition=relationship)

    def restore_unit(self, *, unit: Definition[UnitDefinition]) -> None:
        """Stage restoration of the same reusable unit."""
        require_exact(value=unit.body, expected=UnitDefinition, field="Unit")
        self.restore_definition(definition=unit)

    def _inspected_children(self, *, concept: Concept) -> _ConceptChildren:
        require_exact(value=concept, expected=Concept, field="Inspected concept")
        if concept.status is not DefinitionStatus.APPROVED:
            raise ValueError("Inspect an active concept before editing its children")
        pending = self._capture_lifecycle(before=_capture(definition=concept))
        if concept.id in self._explicit_bodies or isinstance(
            pending, (RetireDefinition, RestoreDefinition)
        ):
            raise ValueError("Child edits conflict with the staged whole-body lifecycle change")
        if pending is not None and pending.before != _capture(definition=concept):
            raise ValueError("Use one inspected revision of the concept")
        current = self._children.get(concept.id)
        if current is not None and current.original != concept:
            raise ValueError("Use the inspected concept revision captured by the builder")
        return current or _ConceptChildren(
            original=concept, attributes=concept.attributes, keys=concept.keys
        )

    def add_attribute(
        self,
        *,
        concept: Concept,
        attribute: AttributeDefinition,
        referenced_definitions: Sequence[Definition] = (),
    ) -> AttributeId:
        """Stage one already-authored attribute without changing the inspected snapshot."""
        current = self._inspected_children(concept=concept)
        require_exact(value=attribute, expected=AttributeDefinition, field="Attribute")
        if any(
            item.id == attribute.id or item.name == attribute.name for item in current.attributes
        ):
            raise ValueError("Use a distinct attribute identity and lookup name")
        bindings = self._with_bindings(definitions=referenced_definitions)
        self._children[concept.id] = replace(
            current,
            attributes=(*current.attributes, attribute),
            changed_attributes=current.changed_attributes | {attribute.id},
        )
        self._bindings = bindings
        return attribute.id

    def edit_attribute(  # noqa: PLR0913 - Preserve each omitted field independently.
        self,
        *,
        concept: Concept,
        attribute: AttributeDefinition,
        display_name: str | Unset = UNSET,
        value_type: AttributeType | Unset = UNSET,
        required: bool | Unset = UNSET,
        collection: CollectionKind | Unset = UNSET,
        min_items: Count | Unset | None = UNSET,
        max_items: Count | Unset | None = UNSET,
        nullability: Nullability | Unset = UNSET,
        constraints: Sequence[ConstraintDefinition] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        referenced_definitions: Sequence[Definition] = (),
    ) -> None:
        """Stage an attribute edit, preserving omitted fields and its stable identity."""
        updated = AttributeDefinition._from_snapshot(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            id=attribute.id,
            name=attribute.name,
            display_name=_selected(value=display_name, existing=attribute.display_name),
            value_type=_selected(value=value_type, existing=attribute.value_type),
            required=_selected(value=required, existing=attribute.required),
            collection=_selected(value=collection, existing=attribute.collection),
            min_items=_selected(value=min_items, existing=attribute.min_items),
            max_items=_selected(value=max_items, existing=attribute.max_items),
            nullability=_selected(value=nullability, existing=attribute.nullability),
            constraints=_selected(value=constraints, existing=attribute.constraints),
            terminology=_selected(value=terminology, existing=attribute.terminology),
        )
        if updated == attribute:
            raise ValueError("Change at least one inspected attribute field")
        bindings = self._with_bindings(definitions=referenced_definitions)
        self._replace_attribute(concept=concept, inspected=attribute, updated=updated)
        self._bindings = bindings

    def remove_attribute(self, *, concept: Concept, attribute: AttributeDefinition) -> None:
        """Stage removal of an exact inspected attribute."""
        self._replace_attribute(concept=concept, inspected=attribute, updated=None)

    def _replace_attribute(
        self,
        *,
        concept: Concept,
        inspected: AttributeDefinition,
        updated: AttributeDefinition | None,
    ) -> None:
        current = self._inspected_children(concept=concept)
        if (
            inspected.id in current.changed_attributes
            or concept.get_attribute(attribute_id=inspected.id) != inspected
        ):
            raise ValueError("Use the original, unmodified attribute from this concept revision")
        self._children[concept.id] = replace(
            current,
            attributes=_replace_child(
                items=current.attributes, inspected=inspected, updated=updated
            ),
            changed_attributes=current.changed_attributes | {inspected.id},
        )

    def add_key(self, *, concept: Concept, key: KeyDefinition) -> KeyId:
        """Stage one key with its generated identity."""
        current = self._inspected_children(concept=concept)
        require_exact(value=key, expected=KeyDefinition, field="Key")
        if any(item.id == key.id or item.name == key.name for item in current.keys):
            raise ValueError("Use a distinct key identity and lookup name")
        self._children[concept.id] = replace(
            current,
            keys=(*current.keys, key),
            changed_keys=current.changed_keys | {key.id},
        )
        return key.id

    def edit_key(
        self,
        *,
        concept: Concept,
        key: KeyDefinition,
        display_name: str | Unset = UNSET,
        attributes: Sequence[AttributeId] | Unset = UNSET,
    ) -> None:
        """Stage an edit of the exact inspected key."""
        updated = KeyDefinition._from_snapshot(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            id=key.id,
            name=key.name,
            display_name=_selected(value=display_name, existing=key.display_name),
            attributes=_selected(value=attributes, existing=key.attributes),
        )
        if updated == key:
            raise ValueError("Change at least one inspected key field")
        self._replace_key(concept=concept, inspected=key, updated=updated)

    def remove_key(self, *, concept: Concept, key: KeyDefinition) -> None:
        """Stage removal of the exact inspected key."""
        self._replace_key(concept=concept, inspected=key, updated=None)

    def _replace_key(
        self,
        *,
        concept: Concept,
        inspected: KeyDefinition,
        updated: KeyDefinition | None,
    ) -> None:
        current = self._inspected_children(concept=concept)
        if (
            inspected.id in current.changed_keys
            or concept.get_key(key_id=inspected.id) != inspected
        ):
            raise ValueError("Use the original, unmodified key from this concept revision")
        self._children[concept.id] = replace(
            current,
            keys=_replace_child(items=current.keys, inspected=inspected, updated=updated),
            changed_keys=current.changed_keys | {inspected.id},
        )

    def _with_child_revisions(
        self,
        *,
        operations: tuple[PlannedOperation, ...],
        reason: str,
    ) -> tuple[PlannedOperation, ...]:
        revised = list(operations)
        for children in self._children.values():
            original = children.original
            body = ConceptDefinition(attributes=children.attributes, keys=children.keys)
            matching = next(
                (
                    (index, item)
                    for index, item in enumerate(revised)
                    if isinstance(item, ReviseDefinition) and item.before.id == original.id
                ),
                None,
            )
            if matching is None:
                revised.append(
                    ReviseDefinition(
                        before=_capture(definition=original),
                        reason=reason,
                        content=AuthoredContent(
                            name=original.name,
                            display_name=original.display_name,
                            meaning=original.meaning,
                            body=body,
                            aliases=original.aliases,
                            terminology=original.terminology,
                            schema_origins=original.schema_origins,
                        ),
                    )
                )
            else:
                index, old = matching
                revised[index] = replace(old, content=replace(old.content, body=body))
        return tuple(revised)

    def include_case(self, *, case: ReviewCase, decision: ReviewAction) -> None:
        """Capture the inspected case version and the chosen leaf action."""
        if case.scope != self._info.scope or case.status is not CaseStatus.PENDING:
            raise ValueError("Supply a pending review case from this model")
        captured = IncludeCase(case_id=case.id, expected_version=case.version, decision=decision)
        self._operations.append(captured)

    def add_change_plan(self, *, plan: ModelChangePlan) -> None:
        """Include immutable, unsubmitted operations at the same inspected revision."""
        if (
            plan.scope != self._info.scope
            or plan.expected_workspace_revision != self._info.revision
        ):
            raise ValueError("Merge only plans built from this inspected workspace")
        bindings = self._bindings.copy()
        for binding in plan.bindings:
            if bindings.setdefault(binding.id, binding) != binding:
                raise ValueError("Inspect a single revision for every bound definition")
        combined = replace(
            plan,
            bindings=tuple(bindings.values()),
            operations=(*self._operations, *plan.operations),
        )
        self._operations = list(combined.operations)
        self._bindings = bindings

    def change_dependencies(self, *, change: DependencyChangeRequest) -> None:
        """Stage a complete desired selection against the inspected workspace pins."""
        require_exact(value=change, expected=DependencyChangeRequest, field="Dependency change")
        if change.before != self._info.dependencies:
            raise ValueError("Reload the workspace and use its current direct dependency pins")
        if self._dependency_change is not None:
            raise ValueError("Stage one dependency change per reviewed plan")
        if any(
            pin.scope.project_id != self._info.scope.project_id or pin.scope == self._info.scope
            for pin in change.after
        ):
            raise ValueError("Use other published models within the same project")
        self._dependency_change = change

    def build_change_plan(self, *, reason: str) -> ModelChangePlan:
        """Freeze the authoring session at its original inspected revision."""
        require_text(value=reason, field="Plan reason")
        last = self._last_plan
        operations = tuple(
            replace(item, reason=reason)
            if _local_operation(
                item=item, creations=self._local_creations, revisions=self._local_revisions
            )
            else item
            for item in self._operations
        )
        operations = self._with_child_revisions(operations=operations, reason=reason)
        bindings = tuple(self._bindings.values())
        if (
            last is not None
            and last.reason == reason
            and last.operations == operations
            and last.bindings == bindings
            and last.dependency_change == self._dependency_change
        ):
            return last
        drafts = tuple(
            item.draft(scope=self._info.scope)
            for item in operations
            if isinstance(item, CreateDefinition)
        )
        owned = {item.id.value for item in drafts}
        issues = validate_model_shapes(
            scope=self._info.scope,
            definitions=(*bindings, *drafts),
            # Confirm qualified revisions in the review transaction, with its exact closure.
            defer_pinned_references=bool(self._info.dependencies),
        )
        if any(
            len(issue.path) < _OWNED_ISSUE_PATH_LENGTH or issue.path[1] in owned for issue in issues
        ):
            raise ValueError("Inspect the plan's typed references and structured value graph")
        plan = ModelChangePlan(
            id=ChangePlanId(value=uuid4().hex),
            scope=self._info.scope,
            expected_workspace_revision=self._info.revision,
            reason=reason,
            bindings=bindings,
            operations=operations,
            dependency_change=self._dependency_change,
        )
        self._last_plan = plan
        return plan


def _reference(
    *,
    value: Definition | DefinitionReference,
    kind: DefinitionKind,
) -> tuple[DefinitionReference, tuple[Definition, ...]]:
    if isinstance(value, Definition):
        if value.kind is not kind:
            raise ValueError("Supply an inspected definition with the requested kind")
        return value.id, (value,)
    return value, ()


def _capture(*, definition: Definition) -> Definition:
    if type(definition) is Definition:
        return definition
    return Definition(
        id=definition.id,
        scope=definition.scope,
        revision=definition.revision,
        name=definition.name,
        display_name=definition.display_name,
        meaning=definition.meaning,
        body=definition.body,
        aliases=definition.aliases,
        terminology=definition.terminology,
        origin=definition.origin,
        status=definition.status,
        basis=definition.basis,
        decision_ids=definition.decision_ids,
        rationale=definition.rationale,
        baseline_definition_id=definition.baseline_definition_id,
        replacement_ids=definition.replacement_ids,
        schema_origins=definition.schema_origins,
    )


def _local_operation(
    *,
    item: PlannedOperation,
    creations: set[DefinitionId],
    revisions: set[DefinitionId],
) -> bool:
    if isinstance(item, CreateDefinition):
        return item.definition_id in creations
    if isinstance(item, IncludeCase):
        return False
    return item.before.id in revisions


def _replace_child[T](*, items: tuple[T, ...], inspected: T, updated: T | None) -> tuple[T, ...]:
    result: list[T] = []
    for item in items:
        if item != inspected:
            result.append(item)
        elif updated is not None:
            result.append(updated)
    return tuple(result)


def _process_bindings(*, body: DefinitionBody) -> tuple[Definition, ...]:
    if not isinstance(body, ProcessDefinition):
        return ()
    captured: list[Definition] = []
    for item in body.referenced_definitions:
        if not isinstance(item, Definition):
            raise TypeError("Use exact inspected SDK model definitions in process activities")
        captured.append(item)
    return tuple(captured)
