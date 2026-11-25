"""Stable caller-owned relation types carried by reviewed relationships."""

from dataclasses import dataclass

from domain_kernel.shared.validators.text_validation import TextValidation


@dataclass(frozen=True, slots=True, kw_only=True)
class RelationTypeRef:
    """Identify a directionally defined relation in a pinned vocabulary."""

    vocabulary: str
    version: str
    code: str

    def __post_init__(self) -> None:
        """Validate the opaque vocabulary and predicate identities."""
        TextValidation.require_text(value=self.vocabulary, field="Relation vocabulary")
        TextValidation.require_text(value=self.version, field="Relation vocabulary version")
        TextValidation.require_text(value=self.code, field="Relation code")
