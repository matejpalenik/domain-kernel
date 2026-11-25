"""Stable caller-owned relation types carried by reviewed relationships."""

from dataclasses import dataclass

from domain_kernel.shared.validation import require_text


@dataclass(frozen=True, slots=True, kw_only=True)
class RelationTypeRef:
    """Identify a directionally defined relation in a pinned vocabulary."""

    vocabulary: str
    version: str
    code: str

    def __post_init__(self) -> None:
        """Validate the opaque vocabulary and predicate identities."""
        require_text(value=self.vocabulary, field="Relation vocabulary")
        require_text(value=self.version, field="Relation vocabulary version")
        require_text(value=self.code, field="Relation code")
