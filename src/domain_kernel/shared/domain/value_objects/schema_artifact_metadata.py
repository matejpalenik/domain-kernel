"""Identify the exact released schema selection and mapping."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation


@dataclass(frozen=True, kw_only=True)
class SchemaArtifactMetadata:
    """Identify the exact released schema selection and mapping."""

    model: ModelVersion
    document_iri: Iri
    mapping_version: str
    root: PinnedDefinitionReference | None = None

    def __post_init__(self) -> None:
        """Verify source and mapping identities."""
        RuntimeTypeValidation.require_exact(
            value=self.model, expected=ModelVersion, field="Schema source"
        )
        RuntimeTypeValidation.require_exact(
            value=self.document_iri, expected=Iri, field="Schema document IRI"
        )
        TextValidation.require_text(value=self.mapping_version, field="Schema mapping")

        if self.root is not None:
            RuntimeTypeValidation.require_exact(
                value=self.root, expected=PinnedDefinitionReference, field="Schema root"
            )
            if self.root.model.scope.project_id != self.model.scope.project_id:
                raise ValueError("Select a schema root in the publication's project")
