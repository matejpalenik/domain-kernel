"""Exact supplied schema provenance attached to an authored definition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class SchemaOrigin:
    """Capture the exact document and location that informed an imported proposal."""

    schema_iri: Iri
    element_iri: Iri | None
    element_path: Sequence[str | int]
    source_hash: ContentHash
    dependency_hashes: Sequence[ContentHash]
    mapping_version: str

    def __post_init__(self) -> None:
        """Retain checked provenance independently of any local identity."""
        RuntimeTypeValidation.require_exact(value=self.schema_iri, expected=Iri, field="Schema IRI")
        if self.element_iri is not None:
            RuntimeTypeValidation.require_exact(
                value=self.element_iri, expected=Iri, field="Element IRI"
            )

        RuntimeTypeValidation.require_exact(
            value=self.source_hash, expected=ContentHash, field="Schema digest"
        )
        TextValidation.require_text(value=self.mapping_version, field="Schema mapping")

        if not SequenceValidation.is_non_string_sequence(value=self.element_path) or any(
            type(item) not in (str, int) for item in self.element_path
        ):
            raise TypeError("Supply the exact element path segments")
        if not self.element_path:
            raise ValueError("Include the imported element's path")

        object.__setattr__(self, "element_path", tuple(self.element_path))
        object.__setattr__(
            self,
            "dependency_hashes",
            SequenceValidation.snapshot_sequence(
                items=self.dependency_hashes, item_type=ContentHash, field="Schema dependencies"
            ),
        )
