"""Host-facing semantic validator and its optional constraint capabilities."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.snapshots import Candidate, ValidationReport
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.domain.enums.constraint_language import ConstraintLanguage


@runtime_checkable
class SemanticValidator(Protocol, metaclass=ABCMeta):
    """Check one exact unpublished candidate and its explicitly selected pack."""

    @property
    @abstractmethod
    def fingerprint(self) -> str:
        """Identify the engine, profile and selected options."""

    @abstractmethod
    async def validate(
        self,
        *,
        candidate: Candidate,
        reference_pack: ReferencePack | None,
    ) -> ValidationReport:
        """Return diagnostics bound to the exact supplied inputs."""


@runtime_checkable
class ConstraintSupport(Protocol, metaclass=ABCMeta):
    """Optional declaration of authored constraint languages an adapter owns."""

    @property
    @abstractmethod
    def constraint_languages(self) -> Sequence[ConstraintLanguage]:
        """Identify supported authored languages independently of inference."""
