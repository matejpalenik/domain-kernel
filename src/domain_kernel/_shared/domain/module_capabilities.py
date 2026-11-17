"""Closed contracts for advertised ontology module extraction."""

from dataclasses import dataclass
from enum import StrEnum, unique

from domain_kernel._shared.domain.reasoning_capabilities import ReasoningProfile, SemanticRegime
from domain_kernel.shared.validation import require_exact


@unique
class ModuleExtractionMethod(StrEnum):
    """An explicit locality or reference extraction algorithm."""

    BOT = "bot"
    TOP = "top"
    STAR = "star"
    MIREOT = "mireot"


@unique
class ModuleGuarantee(StrEnum):
    """The preservation guarantee reported for the selected signature."""

    SIGNATURE_ENTAILMENTS = "signature_entailments"
    NONE = "none"


@dataclass(frozen=True, kw_only=True)
class ModuleExtractionSupport:
    """One verified extraction combination and its advertised guarantee."""

    method: ModuleExtractionMethod
    profile: ReasoningProfile
    regime: SemanticRegime
    guarantee: ModuleGuarantee

    def __post_init__(self) -> None:
        """Validate the exact options and keep reference extraction unguaranteed."""
        require_exact(value=self.method, expected=ModuleExtractionMethod, field="Module method")
        require_exact(value=self.profile, expected=ReasoningProfile, field="Module profile")
        require_exact(value=self.regime, expected=SemanticRegime, field="Module regime")
        require_exact(value=self.guarantee, expected=ModuleGuarantee, field="Module guarantee")
        if (
            self.method is ModuleExtractionMethod.MIREOT
            and self.guarantee is not ModuleGuarantee.NONE
        ):
            raise ValueError("Use MIREOT for reference extraction without an entailment guarantee")
