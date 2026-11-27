"""Detached definition revision in an exact owning model scope."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar

from domain_kernel.modeling.domain.enums.definition_origin import DefinitionOrigin
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.shared.domain.enums.evidence_basis import EvidenceBasis
from domain_kernel.shared.domain.errors.definition_kind_mismatch_error import (
    DefinitionKindMismatchError,
)
from domain_kernel.shared.domain.policies.lookup_naming_policy import LookupNamingPolicy
from domain_kernel.shared.domain.types.definition_body import DefinitionBody
from domain_kernel.shared.domain.validators.definition_body_validation import (
    DefinitionBodyValidation,
)
from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
from domain_kernel.shared.domain.value_objects.schema_origin import SchemaOrigin
from domain_kernel.shared.domain.value_objects.terminology import EMPTY_TERMINOLOGY, Terminology
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind


BodyT_co = TypeVar("BodyT_co", bound=DefinitionBody, covariant=True, default=DefinitionBody)


@dataclass(frozen=True, kw_only=True)
class Definition(Generic[BodyT_co]):
    """Detached definition revision in an exact owning model scope."""

    id: DefinitionId
    scope: ModelScope
    revision: int
    name: str
    display_name: str
    meaning: str
    body: BodyT_co
    aliases: Sequence[str] = ()
    terminology: Terminology = EMPTY_TERMINOLOGY
    origin: DefinitionOrigin = DefinitionOrigin.COMPANY
    status: DefinitionStatus = DefinitionStatus.PROPOSED
    basis: EvidenceBasis = EvidenceBasis.HYPOTHESIS
    decision_ids: Sequence[DecisionId] = ()
    rationale: str | None = None
    baseline_definition_id: DefinitionId | None = None
    replacement_ids: Sequence[DefinitionId] = ()
    schema_origins: Sequence[SchemaOrigin] = field(default=(), metadata={"wire_omit_empty": True})

    evidence: Sequence[Evidence] = field(default=(), metadata={"wire_omit_empty": True})

    def __post_init__(self) -> None:
        """Snapshot one appropriately identified and typed definition revision."""
        RuntimeTypeValidation.require_exact(
            value=self.id, expected=DefinitionId, field="Definition ID"
        )
        RuntimeTypeValidation.require_exact(
            value=self.scope, expected=ModelScope, field="Definition scope"
        )
        RuntimeTypeValidation.require_exact(
            value=self.revision, expected=int, field="Definition revision"
        )
        if self.revision < 1:
            raise ValueError("Definition revision must be positive")

        LookupNamingPolicy.require_lookup_name(name=self.name)
        TextValidation.require_text(value=self.display_name, field="Display name")
        TextValidation.require_text(value=self.meaning, field="Definition meaning")

        DefinitionBodyValidation.require_definition_body(body=self.body)
        RuntimeTypeValidation.require_exact(
            value=self.terminology, expected=Terminology, field="Definition terminology"
        )
        RuntimeTypeValidation.require_exact(
            value=self.origin, expected=DefinitionOrigin, field="Definition origin"
        )

        RuntimeTypeValidation.require_exact(
            value=self.status, expected=DefinitionStatus, field="Definition status"
        )
        RuntimeTypeValidation.require_exact(
            value=self.basis, expected=EvidenceBasis, field="Definition basis"
        )

        if self.baseline_definition_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.baseline_definition_id,
                expected=DefinitionId,
                field="Baseline definition ID",
            )

        if self.rationale is not None:
            TextValidation.require_text(value=self.rationale, field="Definition rationale")

        aliases = SequenceValidation.snapshot_sequence(
            items=self.aliases, item_type=str, field="Aliases"
        )
        decision_ids = SequenceValidation.snapshot_sequence(
            items=self.decision_ids, item_type=DecisionId, field="Decisions"
        )
        replacements = SequenceValidation.snapshot_sequence(
            items=self.replacement_ids, item_type=DefinitionId, field="Replacement IDs"
        )

        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "decision_ids", decision_ids)
        object.__setattr__(self, "replacement_ids", replacements)
        object.__setattr__(
            self,
            "schema_origins",
            SequenceValidation.snapshot_sequence(
                items=self.schema_origins, item_type=SchemaOrigin, field="Schema origins"
            ),
        )

        citations = SequenceValidation.snapshot_sequence(
            items=self.evidence, item_type=Evidence, field="Evidence"
        )
        if len({item.id for item in citations}) != len(citations):
            raise ValueError("Cite each exact source occurrence once")

        object.__setattr__(self, "evidence", citations)

    @property
    def kind(self) -> DefinitionKind:
        """The exact kind of this revision's body."""
        return self.body.kind

    @staticmethod
    def typed_definition[T: DefinitionBody](
        *,
        value: Definition,
        body_type: type[T],
        view_type: type[Definition[T]],
    ) -> Definition[T]:
        """Materialize the exact inspected definition through a typed snapshot view."""
        if not isinstance(value.body, body_type):
            raise DefinitionKindMismatchError

        return view_type(
            id=value.id,
            scope=value.scope,
            revision=value.revision,
            name=value.name,
            display_name=value.display_name,
            meaning=value.meaning,
            body=value.body,
            aliases=value.aliases,
            terminology=value.terminology,
            origin=value.origin,
            status=value.status,
            basis=value.basis,
            decision_ids=value.decision_ids,
            rationale=value.rationale,
            baseline_definition_id=value.baseline_definition_id,
            replacement_ids=value.replacement_ids,
            schema_origins=value.schema_origins,
            evidence=value.evidence,
        )
