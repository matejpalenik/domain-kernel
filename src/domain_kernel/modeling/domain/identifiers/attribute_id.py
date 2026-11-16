"""Stable identity for a model attribute."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class AttributeId(OpaqueIdentifier):
    """Stable identity for a model attribute."""

    def __post_init__(self) -> None:
        """Reject reserved attribute identity spellings."""
        super().__post_init__()
        if self.value in {"@id", "@type"} or self.value.startswith("rel:"):
            raise ValueError("AttributeId uses a reserved spelling")
