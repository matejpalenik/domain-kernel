"""Build connected model change plans with an in-memory authoring session."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Never, final
from uuid import uuid4

from domain_kernel._shared.domain.authoring import (
    AuthoredContent,
    CreateDefinition,
    IncludeCase,
    ModelChangePlan,
)
from domain_kernel._shared.domain.data_shapes import AttributeDefinition, QuantityBinding
from domain_kernel._shared.domain.definitions import (
    ConceptDefinition,
    Definition,
    RelationshipDefinition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
)
from domain_kernel._shared.domain.model_values import Terminology
from domain_kernel._shared.domain.naming import resolve_names
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

    from domain_kernel._shared.domain.authoring import PlannedOperation
    from domain_kernel._shared.domain.data_shapes import KeyDefinition
    from domain_kernel._shared.domain.definitions import DefinitionBody, ValueSetMember
    from domain_kernel._shared.domain.model_values import (
        RelationshipCardinality,
        ValueSetMembership,
    )
    from domain_kernel._shared.domain.ontology_assets import OntologyTermReference
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.models import ReviewCase
    from domain_kernel.shared.contracts import CompanyDefinitionReference, DefinitionReference


_OWNED_ISSUE_PATH_LENGTH = 2


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
        self._local_creations: set[DefinitionId] = set()

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
        bindings = self._bindings.copy()
        for supplied in referenced_definitions:
            bound = _capture(definition=supplied)
            if bound.scope != self._info.scope or bound.status is not DefinitionStatus.APPROVED:
                raise ValueError("Supply approved definitions inspected in this model")
            if bindings.setdefault(bound.id, bound) != bound:
                raise ValueError("Bind only one inspected revision of an existing definition")
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

    def build_change_plan(self, *, reason: str) -> ModelChangePlan:
        """Freeze the authoring session at its original inspected revision."""
        require_text(value=reason, field="Plan reason")
        last = self._last_plan
        operations = tuple(
            replace(item, reason=reason)
            if isinstance(item, CreateDefinition) and item.definition_id in self._local_creations
            else item
            for item in self._operations
        )
        bindings = tuple(self._bindings.values())
        if (
            last is not None
            and last.reason == reason
            and last.operations == operations
            and last.bindings == bindings
        ):
            return last
        drafts = tuple(
            item.draft(scope=self._info.scope)
            for item in operations
            if isinstance(item, CreateDefinition)
        )
        owned = {item.id.value for item in drafts}
        issues = validate_model_shapes(scope=self._info.scope, definitions=(*bindings, *drafts))
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
    )
