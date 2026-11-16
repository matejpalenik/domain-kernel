"""Persistence capabilities for captured candidates and validation reports."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel._shared.application.catalogs import CatalogTransaction
from domain_kernel.review.application.ports import ReviewTransaction

if TYPE_CHECKING:
    from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
    from domain_kernel.modeling.domain.snapshots import Candidate, ReviewSnapshot, ValidationReport
    from domain_kernel.shared.contracts import ModelScope


@dataclass(frozen=True, kw_only=True)
class CompiledSnapshot:
    """An exact compiled candidate with its independently captured review state."""

    candidate: Candidate
    review: ReviewSnapshot


class CompilationRepository(Protocol, metaclass=ABCMeta):
    """Persist immutable candidate and validation identities."""

    @abstractmethod
    async def add_candidate(self, *, snapshot: CompiledSnapshot) -> None:
        """Save the complete candidate and its review inputs."""

    @abstractmethod
    async def get_candidate(
        self, *, scope: ModelScope, candidate_id: CandidateId
    ) -> CompiledSnapshot:
        """Read one exact candidate from its owning model."""

    @abstractmethod
    async def add_report(self, *, report: ValidationReport) -> None:
        """Save a validation report without mutating its candidate."""


@runtime_checkable
class CompilationTransaction(CatalogTransaction, ReviewTransaction, Protocol, metaclass=ABCMeta):
    """Operation resources needed to compile or validate an exact model."""

    @property
    @abstractmethod
    def compilation(self) -> CompilationRepository:
        """Return the bound candidate and validation repository."""
