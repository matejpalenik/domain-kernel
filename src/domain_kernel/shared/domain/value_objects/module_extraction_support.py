"""One verified extraction combination and its advertised guarantee."""

from dataclasses import dataclass

from domain_kernel.shared.domain.enums.module_extraction_method import ModuleExtractionMethod
from domain_kernel.shared.domain.enums.module_guarantee import ModuleGuarantee
from domain_kernel.shared.domain.enums.reasoning_profile import ReasoningProfile
from domain_kernel.shared.domain.enums.semantic_regime import SemanticRegime
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class ModuleExtractionSupport:
    """One verified extraction combination and its advertised guarantee."""

    method: ModuleExtractionMethod
    profile: ReasoningProfile
    regime: SemanticRegime
    guarantee: ModuleGuarantee

    def __post_init__(self) -> None:
        """Validate the exact options and keep reference extraction unguaranteed."""
        RuntimeTypeValidation.require_exact(
            value=self.method, expected=ModuleExtractionMethod, field="Module method"
        )
        RuntimeTypeValidation.require_exact(
            value=self.profile, expected=ReasoningProfile, field="Module profile"
        )
        RuntimeTypeValidation.require_exact(
            value=self.regime, expected=SemanticRegime, field="Module regime"
        )
        RuntimeTypeValidation.require_exact(
            value=self.guarantee, expected=ModuleGuarantee, field="Module guarantee"
        )

        if (
            self.method is ModuleExtractionMethod.MIREOT
            and self.guarantee is not ModuleGuarantee.NONE
        ):
            raise ValueError("Use MIREOT for reference extraction without an entailment guarantee")
