"""Public handle for a scoped project and its model workspaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from domain_kernel._composition import open_models
from domain_kernel.discovery.application.extraction import Extraction
from domain_kernel.modeling.api.model import Model
from domain_kernel.shared.errors import MissingCapabilityError
from domain_kernel.sources.application.batch import SourceBatch
from domain_kernel.sources.application.service import CaptureRequest, Sources

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel._shared.application.catalogs import CatalogTransaction
    from domain_kernel._shared.application.inference import ExtractionSettings
    from domain_kernel._shared.application.persistence import UnitOfWorkFactory
    from domain_kernel._shared.domain.audit import AuditRecord
    from domain_kernel.bundles import DomainModelBundle
    from domain_kernel.modeling.application.exports import ExportDestination
    from domain_kernel.modeling.application.validation import CompositeModelValidator
    from domain_kernel.modeling.domain.enums.model_kind import ModelKind
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.modeling.domain.snapshots import PublicationRules
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.projects.domain.project_info import ProjectInfo
    from domain_kernel.reconciliation.application.ports import SimilarityScorer
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.contracts import ModelVersion, Page
    from domain_kernel.shared.identifiers.page_cursor import PageCursor
    from domain_kernel.sources.application.contracts import (
        BatchIngestionResult,
        CopyTo,
        SourceDescriptor,
        SourceFolder,
        SourceInput,
    )
    from domain_kernel.sources.application.service import SourceRuntime
    from domain_kernel.sources.domain.identifiers.source_id import SourceId
    from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
    from domain_kernel.sources.domain.models import (
        Evidence,
        EvidenceContent,
        IngestedSource,
        OriginalCopy,
        Source,
        SourceProfile,
        SourceRevision,
    )


@final
class Project:
    """Access a project's named modeling workspaces and durable audit history."""

    def __init__(  # noqa: PLR0913 - Exact workspace and configured capabilities.
        self,
        *,
        info: ProjectInfo,
        resources: UnitOfWorkFactory[CatalogTransaction],
        publication_rules: PublicationRules,
        source_runtime: SourceRuntime | None = None,
        extraction_settings: ExtractionSettings | None = None,
        similarity_scorer: SimilarityScorer | None = None,
        artifact_destinations: Mapping[str, ExportDestination] | None = None,
        validator: CompositeModelValidator | None = None,
    ) -> None:
        """Bind loaded project identity to the client's resource factory."""
        self._info = info
        self._resources = resources
        self._publication_rules = publication_rules
        self._source_runtime = source_runtime
        self._extraction_settings = extraction_settings
        self._similarity_scorer = similarity_scorer
        self._artifact_destinations = artifact_destinations
        self._validator = validator

    @property
    def id(self) -> ProjectId:
        """Return the project's immutable identity."""
        return self._info.id

    @property
    def name(self) -> str:
        """Return the exact lookup name."""
        return self._info.name

    @property
    def display_name(self) -> str:
        """Return the label captured for this handle."""
        return self._info.display_name

    async def create_model(  # noqa: PLR0913 - Explicit public intent and stable names.
        self,
        *,
        actor: str,
        kind: ModelKind,
        description: str,
        display_name: str | None = None,
        name: str | None = None,
        reference_pack: ReferencePack | None = None,
        copy_from: DomainModelBundle | None = None,
        dependencies: Sequence[ModelVersion] = (),
    ) -> Model:
        """Create an independent work area for the specified modeling intent."""
        async with open_models(resources=self._resources, project_id=self.id) as models:
            info = await models.create(
                actor=actor,
                kind=kind,
                reference_pack=reference_pack,
                copy_from=copy_from,
                dependencies=dependencies,
                description=description,
                display_name=display_name,
                name=name,
            )
        return Model(
            info=info,
            resources=self._resources,
            publication_rules=self._publication_rules,
            artifact_destinations=self._artifact_destinations,
            validator=self._validator,
            extraction=self._extraction(),
            similarity_scorer=self._similarity_scorer,
        )

    async def get_model(self, *, name: str) -> Model:
        """Reopen a model by its exact project-local name."""
        async with open_models(resources=self._resources, project_id=self.id) as models:
            info = await models.get(name=name)
        return Model(
            info=info,
            resources=self._resources,
            publication_rules=self._publication_rules,
            artifact_destinations=self._artifact_destinations,
            validator=self._validator,
            extraction=self._extraction(),
            similarity_scorer=self._similarity_scorer,
        )

    async def list_models(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[ModelInfo]:
        """Page through this project's model metadata."""
        async with open_models(resources=self._resources, project_id=self.id) as models:
            return await models.list(limit=limit, cursor=cursor)

    def _extraction(self) -> Extraction | None:
        if self._extraction_settings is None:
            return None
        return Extraction(
            settings=self._extraction_settings,
            sources=self._sources(),
            resources=self._resources,
        )

    def _sources(self) -> Sources:
        if self._source_runtime is None:
            raise MissingCapabilityError(message="Configure project source capabilities")
        return Sources(project_id=self.id, resources=self._resources, runtime=self._source_runtime)

    async def ingest_source(  # noqa: PLR0913 - Explicit name, destination and replay key.
        self,
        *,
        actor: str,
        source: SourceDescriptor,
        display_name: str | None = None,
        name: str | None = None,
        retain_original: CopyTo | None = None,
        idempotency_key: str | None = None,
    ) -> IngestedSource:
        """Acquire a new named source and record its first immutable revision."""
        return await self._sources().ingest(
            actor=actor,
            request=CaptureRequest(
                source=source,
                name=name,
                display_name=display_name,
                retain_original=retain_original,
                idempotency_key=idempotency_key,
            ),
        )

    async def ingest_sources(
        self,
        *,
        actor: str,
        sources: Sequence[SourceInput | SourceFolder],
        max_concurrent_sources: int | None = None,
        max_files: int | None = None,
    ) -> BatchIngestionResult:
        """Capture a bounded selection and ingest each distinct file independently."""
        if self._source_runtime is None:
            raise MissingCapabilityError(message="Configure project source capabilities")
        return await SourceBatch(
            project_id=self.id,
            resources=self._resources,
            runtime=self._source_runtime,
            sources=self._sources(),
        ).ingest(
            actor=actor,
            inputs=sources,
            max_concurrent_sources=max_concurrent_sources,
            max_files=max_files,
        )

    async def ingest_source_revision(
        self,
        *,
        actor: str,
        source_id: SourceId,
        source: SourceDescriptor,
        retain_original: CopyTo | None = None,
        idempotency_key: str | None = None,
    ) -> IngestedSource:
        """Accept exact bytes under an existing source identity."""
        return await self._sources().ingest(
            actor=actor,
            request=CaptureRequest(
                source=source,
                source_id=source_id,
                retain_original=retain_original,
                idempotency_key=idempotency_key,
            ),
        )

    async def get_evidence(self, *, evidence: Evidence) -> EvidenceContent:
        """Resolve the exact recorded citation through its configured source provider."""
        return await self._sources().get_evidence(evidence=evidence)

    async def get_source(
        self,
        *,
        name: str | None = None,
        source_id: SourceId | None = None,
    ) -> Source:
        """Read an exact source by its project-local name or ID."""
        return await self._sources().get(name=name, source_id=source_id)

    async def list_sources(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[Source]:
        """List available source identities without opening originals."""
        return await self._sources().list(limit=limit, cursor=cursor)

    async def get_source_revision(
        self,
        *,
        source_id: SourceId,
        revision_id: SourceRevisionId,
    ) -> SourceRevision:
        """Read the exact immutable acquisition metadata."""
        return await self._sources().get_revision(source_id=source_id, revision_id=revision_id)

    async def list_source_revisions(
        self,
        *,
        source_id: SourceId,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[SourceRevision]:
        """List the revisions recorded under one source ID."""
        return await self._sources().list_revisions(source_id=source_id, limit=limit, cursor=cursor)

    async def profile_source(
        self,
        *,
        actor: str,
        revision: SourceRevision,
        processing_fingerprint: str | None = None,
    ) -> SourceProfile:
        """Read the latest profile or the profile for an exact processing capture."""
        return await self._sources().profile(
            actor=actor, revision=revision, processing_fingerprint=processing_fingerprint
        )

    async def copy_source_original(
        self,
        *,
        actor: str,
        revision: SourceRevision,
        destination: CopyTo,
        idempotency_key: str | None = None,
    ) -> OriginalCopy:
        """Copy or verify the exact captured file revision at an approved store."""
        return await self._sources().copy_original(
            actor=actor,
            revision=revision,
            destination=destination,
            idempotency_key=idempotency_key,
        )

    async def get_audit_history(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[AuditRecord]:
        """Inspect attributed events across this project and its models."""
        async with self._resources() as transaction, transaction.begin():
            return await transaction.audit.list(
                project_id=self.id,
                model_id=None,
                limit=limit,
                cursor=cursor,
            )
