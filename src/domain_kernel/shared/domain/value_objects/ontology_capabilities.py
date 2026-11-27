"""Identity and supported transformations of an explicitly selected adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.enums.ontology_syntax import OntologySyntax
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.module_extraction_support import (
    ModuleExtractionSupport,
)
from domain_kernel.shared.domain.value_objects.reasoning_support import ReasoningSupport
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class OntologyCapabilities:
    """Identity and supported transformations of an explicitly selected adapter."""

    adapter_id: str
    adapter_version: str
    extraction: Sequence[ModuleExtractionSupport] = field(
        default=(), metadata={"wire_omit_empty": True}
    )
    reasoning: Sequence[ReasoningSupport] = field(default=(), metadata={"wire_omit_empty": True})
    parse_syntaxes: Sequence[OntologySyntax] = ()
    serialize_syntaxes: Sequence[OntologySyntax] = ()
    datatypes: Sequence[Iri] = ()
    feature_ids: Sequence[str] = ()

    def __post_init__(self) -> None:
        """Capture advertised capabilities as immutable typed choices."""
        TextValidation.require_text(value=self.adapter_id, field="Ontology adapter ID")
        TextValidation.require_text(value=self.adapter_version, field="Ontology adapter version")

        extraction = SequenceValidation.snapshot_sequence(
            items=self.extraction, item_type=ModuleExtractionSupport, field="Module capabilities"
        )
        if len({(item.method, item.profile, item.regime) for item in extraction}) != len(
            extraction
        ):
            raise ValueError("Advertise one extraction contract per method, profile and regime")
        object.__setattr__(self, "extraction", extraction)

        reasoning = SequenceValidation.snapshot_sequence(
            items=self.reasoning, item_type=ReasoningSupport, field="Reasoning capabilities"
        )
        if len({(item.profile, item.regime, item.task) for item in reasoning}) != len(reasoning):
            raise ValueError("Advertise one result contract per reasoning profile, regime and task")
        object.__setattr__(self, "reasoning", reasoning)

        for name, values in (
            ("parse_syntaxes", self.parse_syntaxes),
            ("serialize_syntaxes", self.serialize_syntaxes),
        ):
            object.__setattr__(
                self,
                name,
                SequenceValidation.snapshot_sequence(
                    items=values, item_type=OntologySyntax, field=name
                ),
            )

        object.__setattr__(
            self,
            "datatypes",
            SequenceValidation.snapshot_sequence(
                items=self.datatypes,
                item_type=Iri,
                field="Supported datatypes",
            ),
        )
        object.__setattr__(
            self,
            "feature_ids",
            SequenceValidation.snapshot_sequence(
                items=self.feature_ids,
                item_type=str,
                field="Semantic feature IDs",
            ),
        )
