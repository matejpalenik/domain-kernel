"""Ports for portable semantic mappings."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.interchange import (
        ProjectionAssessment,
        RdfProjectionRequest,
        SemanticProjection,
        ValidationGraphs,
    )
    from domain_kernel.modeling.domain.snapshots import Candidate, DomainModelBundle
    from domain_kernel.reference_packs.api.packs import ReferencePack


class SemanticProjector(Protocol, metaclass=ABCMeta):
    """Assess and project the same exact published graph."""

    @abstractmethod
    def assess(
        self,
        *,
        bundle: DomainModelBundle,
        request: RdfProjectionRequest,
    ) -> ProjectionAssessment:
        """Return coverage and obligations for all roles in the exact closure."""

    @abstractmethod
    def project(
        self,
        *,
        bundle: DomainModelBundle,
        request: RdfProjectionRequest,
    ) -> SemanticProjection:
        """Render the complete supported representation after the shared assessment."""

    @abstractmethod
    def validation_graphs(
        self,
        *,
        candidate: Candidate,
        reference_pack: ReferencePack | None,
        mapping_version: str,
    ) -> ValidationGraphs:
        """Map candidate records for metadata validation without a publication."""
