"""Ports for portable semantic mappings."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.ontology_assets import Iri
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.modeling.domain.interchange import (
        LinkmlProjectionRequest,
        LinkmlSyntax,
        ProjectionAssessment,
        RdfProjectionRequest,
        SemanticProjection,
        ValidationGraphs,
    )
    from domain_kernel.modeling.domain.linkml import (
        LinkmlProjection,
        SchemaDocument,
        SchemaImportResult,
    )
    from domain_kernel.modeling.domain.models import ModelInfo
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


class LinkmlMapper(Protocol, metaclass=ABCMeta):
    """Assess and interchange the same bounded set of released business shapes."""

    @abstractmethod
    def assess(
        self, *, bundle: DomainModelBundle, request: LinkmlProjectionRequest
    ) -> ProjectionAssessment:
        """Report exact availability, coverage and host obligations."""

    @abstractmethod
    def project(
        self,
        *,
        bundle: DomainModelBundle,
        base_iri: Iri,
        definition_ids: Sequence[DefinitionId] | None,
        syntax: LinkmlSyntax,
        mapping_version: str,
    ) -> LinkmlProjection:
        """Render the same checked selection into native LinkML and its manifest."""

    @abstractmethod
    def load(  # noqa: PLR0913 - Explicit transport, destination, mapping and limits.
        self,
        *,
        document: SchemaDocument,
        dependencies: Sequence[SchemaDocument],
        model_info: ModelInfo,
        reason: str,
        mapping_version: str,
        max_bytes: int,
    ) -> SchemaImportResult:
        """Create a detached plan from supplied bytes and the inspected destination."""
