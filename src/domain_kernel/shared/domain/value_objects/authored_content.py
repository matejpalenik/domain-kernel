"""Complete explicit content for a proposed definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.policies.naming import require_lookup_name
from domain_kernel.shared.domain.value_objects.schema_origin import SchemaOrigin
from domain_kernel.shared.domain.value_objects.terminology import Terminology
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.types.definition_body import DefinitionBody


@dataclass(frozen=True, kw_only=True)
class AuthoredContent:
    """Complete explicit content for a proposed definition."""

    name: str
    display_name: str
    meaning: str
    body: DefinitionBody
    aliases: Sequence[str] = ()
    terminology: Terminology = field(default_factory=Terminology)
    schema_origins: Sequence[SchemaOrigin] = field(default=(), metadata={"wire_omit_empty": True})

    def __post_init__(self) -> None:
        """Validate exact names and detach descriptive metadata."""
        require_lookup_name(name=self.name)
        TextValidation.require_text(value=self.display_name, field="Display name")
        TextValidation.require_text(value=self.meaning, field="Meaning")
        RuntimeTypeValidation.require_exact(
            value=self.terminology, expected=Terminology, field="Terminology"
        )
        object.__setattr__(
            self,
            "aliases",
            SequenceValidation.snapshot_sequence(
                items=self.aliases, item_type=str, field="Aliases"
            ),
        )
        object.__setattr__(
            self,
            "schema_origins",
            SequenceValidation.snapshot_sequence(
                items=self.schema_origins, item_type=SchemaOrigin, field="Schema origins"
            ),
        )
