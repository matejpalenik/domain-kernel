"""Typed choices available for manual definition review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

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
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

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


type ReviewAction = Accept | EditDefinition | Reject | MapToReference | ApproveLocalExtension
