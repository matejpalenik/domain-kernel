"""Ports for portable semantic mappings."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.interchange import (
        ProjectionAssessment,
        RdfProjectionRequest,
        SemanticProjection,
    )
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle


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
