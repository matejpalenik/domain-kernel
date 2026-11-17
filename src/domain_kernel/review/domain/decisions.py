"""Typed choices available for manual definition review."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Literal, Self

from domain_kernel._shared.domain.definitions import (
    Definition,
    require_definition_body,
    typed_definition,
)
from domain_kernel._shared.domain.model_values import Terminology
from domain_kernel._shared.domain.naming import require_lookup_name
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.reference_packs.domain.contracts import (
    MappingRelation,
    ReferenceAlignment,
    ReferenceDefinition,
)
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence
from domain_kernel.sources.domain.models import Evidence, SourceRevision
from domain_kernel.sources.domain.statements import Person, StatementOrigin, require_statement_time

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from domain_kernel._shared.domain.definitions import DefinitionBody
    from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
        ReferenceDefinitionId,
    )


@dataclass(frozen=True, kw_only=True)
class Accept:
    """Accept the effect captured in the inspected review case."""

    reason: str
    kind: Literal["accept"] = "accept"

    def __post_init__(self) -> None:
        """Preserve the explicit review action and reason."""
        require_text(value=self.reason, field="Decision reason")
        require_exact(value=self.kind, expected=str, field="Decision kind")
        if self.kind != "accept":
            raise ValueError("Use the accept decision kind")


@dataclass(frozen=True, kw_only=True)
class EditDefinition:
    """Accept edited content for the same proposed identity and lookup name."""

    definition_id: DefinitionId
    name: str
    display_name: str
    meaning: str
    body: DefinitionBody
    reason: str
    aliases: Sequence[str] = ()
    terminology: Terminology = field(default_factory=Terminology)
    kind: Literal["edit_definition"] = "edit_definition"

    def __post_init__(self) -> None:
        """Validate the proposed replacement content and freeze aliases."""
        require_text(value=self.reason, field="Decision reason")
        require_exact(value=self.kind, expected=str, field="Decision kind")
        if self.kind != "edit_definition":
            raise ValueError("Use the edit_definition decision kind")
        require_exact(value=self.definition_id, expected=DefinitionId, field="Definition identity")
        require_lookup_name(name=self.name)
        require_text(value=self.display_name, field="Display name")
        require_text(value=self.meaning, field="Definition meaning")
        require_exact(value=self.terminology, expected=Terminology, field="Terminology")
        require_definition_body(body=self.body)
        aliases = snapshot_sequence(items=self.aliases, item_type=str, field="Definition aliases")
        object.__setattr__(self, "aliases", aliases)


@dataclass(frozen=True, kw_only=True)
class Reject:
    """Resolve a case by declining its proposed effects."""

    reason: str
    kind: Literal["reject"] = "reject"

    def __post_init__(self) -> None:
        """Preserve the explicit review action and reason."""
        require_text(value=self.reason, field="Decision reason")
        require_exact(value=self.kind, expected=str, field="Decision kind")
        if self.kind != "reject":
            raise ValueError("Use the reject decision kind")


@dataclass(frozen=True, kw_only=True, init=False)
class MapToReference:
    """An explicit business judgement about an inspected local and reference meaning."""

    local_definition: Definition
    reference_definition: ReferenceDefinition
    reference_pack: ReferencePackPin
    relation: MappingRelation
    reason: str
    kind: Literal["map_to_reference"] = "map_to_reference"

    def __init__(
        self,
        *,
        local_definition: Definition,
        reference_definition: ReferenceDefinition,
        relation: MappingRelation,
        reason: str,
    ) -> None:
        """Bind both exact snapshots and the reference member's containing pack."""
        require_exact(
            value=reference_definition, expected=ReferenceDefinition, field="Reference definition"
        )
        pack = reference_definition.reference_pack
        if pack is None:
            raise ValueError("Inspect a reference definition in its materialized pack")
        self._capture(
            local_definition=local_definition,
            reference_definition=reference_definition,
            reference_pack=pack,
            relation=relation,
            reason=reason,
        )

    def _capture(
        self,
        *,
        local_definition: Definition,
        reference_definition: ReferenceDefinition,
        reference_pack: ReferencePackPin,
        relation: MappingRelation,
        reason: str,
    ) -> None:
        require_exact(value=relation, expected=MappingRelation, field="Business mapping relation")
        require_exact(
            value=reference_pack, expected=ReferencePackPin, field="Reference mapping pin"
        )
        require_exact(
            value=reference_definition, expected=ReferenceDefinition, field="Reference definition"
        )
        require_text(value=reason, field="Mapping reason")
        inspected = typed_definition(
            value=local_definition,
            body_type=type(local_definition.body),
            view_type=Definition,
        )
        object.__setattr__(self, "local_definition", inspected)
        object.__setattr__(
            self, "reference_definition", reference_definition.associate(pin=reference_pack)
        )
        object.__setattr__(self, "reference_pack", reference_pack)
        object.__setattr__(self, "relation", relation)
        object.__setattr__(self, "reason", reason)

    @classmethod
    def restore(  # noqa: PLR0913 - Restore every exact stored field.
        cls,
        *,
        local_definition: Definition,
        reference_definition: ReferenceDefinition,
        reference_pack: ReferencePackPin,
        relation: MappingRelation,
        reason: str,
        kind: str,
    ) -> MapToReference:
        """Restore the reference association from the explicit persisted pack pin."""
        if kind != "map_to_reference":
            raise ValueError("Use the declared mapping decision kind")
        restored = cls.__new__(cls)
        restored._capture(  # noqa: SLF001 - Restore the declared inspected record.
            local_definition=local_definition,
            reference_definition=reference_definition,
            reference_pack=reference_pack,
            relation=relation,
            reason=reason,
        )
        return restored

    @property
    def definition_id(self) -> DefinitionId:
        """Return the reviewed local identity."""
        return self.local_definition.id

    @property
    def definition_revision(self) -> int:
        """Return the reviewed local revision."""
        return self.local_definition.revision

    @property
    def reference_id(self) -> ReferenceDefinitionId:
        """Return the exact reference identity."""
        return self.reference_definition.id


@dataclass(frozen=True, kw_only=True)
class ApproveLocalExtension:
    """Review an application-owned definition under its current local scope."""

    definition_id: DefinitionId
    reason: str
    relationships: Sequence[ReferenceAlignment] = ()
    kind: Literal["local_extension"] = "local_extension"

    def __post_init__(self) -> None:
        """Keep explicit links separate from the local-extension decision itself."""
        require_exact(value=self.definition_id, expected=DefinitionId, field="Local extension ID")
        require_text(value=self.reason, field="Extension reason")
        if self.kind != "local_extension":
            raise ValueError("Use the declared local extension decision kind")
        object.__setattr__(
            self,
            "relationships",
            snapshot_sequence(
                items=self.relationships,
                item_type=ReferenceAlignment,
                field="Extension relationships",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class MapToDefinition:
    """Assign one source occurrence to an exact inspected local meaning."""

    definition: Definition
    reason: str
    kind: Literal["map_to_definition"] = "map_to_definition"

    def __post_init__(self) -> None:
        """Capture the exact definition independently of any typed read view."""
        _check_choice(kind=self.kind, expected="map_to_definition", reason=self.reason)
        inspected = typed_definition(
            value=self.definition,
            body_type=type(self.definition.body),
            view_type=Definition,
        )
        object.__setattr__(self, "definition", inspected)

    @property
    def definition_id(self) -> DefinitionId:
        """Return the inspected local identity."""
        return self.definition.id

    @property
    def definition_revision(self) -> int:
        """Return the inspected local revision."""
        return self.definition.revision


@dataclass(frozen=True, kw_only=True)
class Exclude:
    """Record why the inspected occurrence is outside the selected scope."""

    scope_text: str
    reason: str
    kind: Literal["exclude"] = "exclude"

    def __post_init__(self) -> None:
        """Retain the reviewed scope and rationale."""
        _check_choice(kind=self.kind, expected="exclude", reason=self.reason)
        require_text(value=self.scope_text, field="Excluded scope")


@dataclass(frozen=True, kw_only=True)
class Defer:
    """Record an unresolved question for the inspected source interpretation."""

    question: str
    reason: str
    kind: Literal["defer"] = "defer"

    def __post_init__(self) -> None:
        """Retain the open question and rationale."""
        _check_choice(kind=self.kind, expected="defer", reason=self.reason)
        require_text(value=self.question, field="Open question")


@dataclass(frozen=True, kw_only=True)
class KeepNonblockingQuestion:
    """Review an optional open question with its exact scope and rationale."""

    scope_text: str
    reason: str
    kind: Literal["keep_nonblocking_question"] = "keep_nonblocking_question"

    def __post_init__(self) -> None:
        """Keep the scope explanation with the decision."""
        _check_choice(kind=self.kind, expected="keep_nonblocking_question", reason=self.reason)
        require_text(value=self.scope_text, field="Question scope")


@unique
class ConfirmationMethod(StrEnum):
    """How the host attributes the confirmation."""

    RECORDED = "recorded"
    AUTHENTICATED = "authenticated"


@dataclass(frozen=True, kw_only=True)
class Confirmation:
    """An attributed confirmation with independently selected evidence."""

    confirmed_by: Person
    method: ConfirmationMethod
    confirmed_at: datetime
    evidence: Sequence[Evidence]
    recorded_by: str
    recorded_at: datetime
    authority: str
    authenticated_actor: str | None = None

    def __post_init__(self) -> None:
        """Check attribution, timestamps, the selected method and its evidence."""
        try:
            require_exact(value=self.confirmed_by, expected=Person, field="Confirmer")
            require_exact(
                value=self.method, expected=ConfirmationMethod, field="Confirmation method"
            )
            require_statement_time(value=self.confirmed_at)
            require_statement_time(value=self.recorded_at)
            require_text(value=self.recorded_by, field="Recorder")
            require_text(value=self.authority, field="Confirmation authority")
            evidence = snapshot_sequence(
                items=self.evidence, item_type=Evidence, field="Confirmation evidence"
            )
            if self.authenticated_actor is not None:
                require_text(value=self.authenticated_actor, field="Authenticated actor")
        except (TypeError, ValueError):
            raise InvalidDecisionError(
                message="Supply exact confirmation attribution and evidence."
            ) from None
        if (
            not evidence
            or len({item.id for item in evidence}) != len(evidence)
            or self.recorded_at < self.confirmed_at
            or (self.method is ConfirmationMethod.AUTHENTICATED)
            != (self.authenticated_actor is not None)
        ):
            raise InvalidDecisionError(
                message="Check the confirmation method, timestamps and evidence."
            )
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True, kw_only=True)
class AnswerQuestion:
    """Record the host's attributed answer and any separately supplied confirmation."""

    answer: str
    reason: str
    confirmation: Confirmation | None = None
    kind: Literal["answer_question"] = "answer_question"

    def __post_init__(self) -> None:
        """Validate the explicit answer and its optional confirmation record."""
        _check_choice(kind=self.kind, expected="answer_question", reason=self.reason)
        require_text(value=self.answer, field="Answer")
        if self.confirmation is not None:
            require_exact(
                value=self.confirmation, expected=Confirmation, field="Answer confirmation"
            )


@dataclass(frozen=True, kw_only=True)
class ConfirmStatement:
    """Prepare a confirmation decision over an exact separately captured statement."""

    confirmation: Confirmation
    reason: str
    kind: Literal["confirm_statement"] = "confirm_statement"

    def __post_init__(self) -> None:
        """Require an explicit confirmation and reason."""
        try:
            _check_choice(kind=self.kind, expected="confirm_statement", reason=self.reason)
            require_exact(value=self.confirmation, expected=Confirmation, field="Confirmation")
        except (TypeError, ValueError):
            raise InvalidDecisionError(message="Supply the confirmation and its reason.") from None

    @classmethod
    def _from_statement(
        cls,
        *,
        revision: SourceRevision,
        evidence: Sequence[Evidence],
        authority: str,
        reason: str,
    ) -> Self:
        """Adapt exact statement provenance without reading a clock or retrieving evidence."""
        try:
            require_exact(value=revision, expected=SourceRevision, field="Statement revision")
            citations = snapshot_sequence(
                items=evidence, item_type=Evidence, field="Statement evidence"
            )
        except (TypeError, ValueError):
            raise InvalidDecisionError(
                message="Select the exact statement and its evidence."
            ) from None
        origin = revision.origin
        if not isinstance(origin, StatementOrigin) or origin.stated_at is None:
            raise InvalidDecisionError(message="Select a statement with a known original time.")
        if not citations or any(
            item.source != revision or item.processing.source != revision for item in citations
        ):
            raise InvalidDecisionError(message="Select evidence from the exact statement revision.")
        return cls(
            reason=reason,
            confirmation=Confirmation(
                confirmed_by=origin.speaker,
                method=ConfirmationMethod.RECORDED,
                confirmed_at=origin.stated_at,
                evidence=citations,
                recorded_by=origin.recorded_by,
                recorded_at=origin.recorded_at,
                authority=authority,
            ),
        )


def _check_choice(*, kind: str, expected: str, reason: str) -> None:
    require_exact(value=kind, expected=str, field="Decision kind")
    if kind != expected:
        raise ValueError("Use the declared decision kind")
    require_text(value=reason, field="Decision reason")


type ContentChangeAction = (
    Accept | EditDefinition | MapToDefinition | MapToReference | ApproveLocalExtension | Exclude
)
type ReviewAction = (
    ContentChangeAction
    | Reject
    | Defer
    | KeepNonblockingQuestion
    | AnswerQuestion
    | ConfirmStatement
)
