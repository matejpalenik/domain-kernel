"""Python SDK entry point for configuration and workspace selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from domain_kernel._composition import (
    ClientIntegrations,
    configuration_report,
    open_projects,
    source_runtime,
    transaction_resources,
)
from domain_kernel._settings import load_settings
from domain_kernel.configuration import FilesystemReader
from domain_kernel.modeling.domain.snapshots import PublicationRules
from domain_kernel.project import Project
from domain_kernel.reference_packs.application.catalog import Catalog
from domain_kernel.shared.contracts import Page
from domain_kernel.shared.errors import MissingCapabilityError, ReferencePackNotFoundError
from domain_kernel.shared.validation import require_text
from domain_kernel.sources.infrastructure.filesystem_reader import FilesystemSourceReader

if TYPE_CHECKING:
    from domain_kernel.configuration import ConfigurationInput
    from domain_kernel.diagnostics import ConfigurationReport
    from domain_kernel.projects.domain.project_info import ProjectInfo
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


@final
class Client:
    """Configure SDK resources and access projects by their stable names."""

    def __init__(
        self,
        *,
        config: ConfigurationInput | None = None,
        integrations: ClientIntegrations | None = None,
    ) -> None:
        """Capture settings and host integrations without database I/O."""
        self._settings = load_settings(config=config)
        self._publication_rules = PublicationRules(
            allow_reviewed_nonblocking_questions=(
                self._settings.configuration.publication.allow_reviewed_nonblocking_questions
            ),
        )
        self._integrations = ClientIntegrations() if integrations is None else integrations
        self._resources = transaction_resources(
            settings=self._settings,
            integrations=self._integrations,
        )
        self._source_runtime = source_runtime(
            settings=self._settings,
            integrations=self._integrations,
        )

    def inspect_configuration(self) -> ConfigurationReport:
        """Return the captured redacted configuration without I/O."""
        return configuration_report(settings=self._settings, integrations=self._integrations)

    async def create_project(
        self,
        *,
        actor: str,
        display_name: str | None = None,
        name: str | None = None,
    ) -> Project:
        """Create a project and return its stable workspace handle."""
        async with open_projects(resources=self._resources) as projects:
            info = await projects.create(actor=actor, display_name=display_name, name=name)
        return Project(
            info=info,
            resources=self._resources,
            publication_rules=self._publication_rules,
            source_runtime=self._source_runtime,
        )

    async def get_project(self, *, name: str) -> Project:
        """Open an existing project by exact name."""
        async with open_projects(resources=self._resources) as projects:
            info = await projects.get(name=name)
        return Project(
            info=info,
            resources=self._resources,
            publication_rules=self._publication_rules,
            source_runtime=self._source_runtime,
        )

    async def list_projects(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[ProjectInfo]:
        """Page through the available projects."""
        async with open_projects(resources=self._resources) as projects:
            return await projects.list(limit=limit, cursor=cursor)

    def _catalog(self) -> Catalog | None:
        config = self._settings.configuration
        approved = config.reference_packs
        if approved is None:
            return None
        if not isinstance(approved.reader, FilesystemReader):
            raise MissingCapabilityError(
                message="Configure a reader for the selected catalog backend"
            )
        return Catalog(
            reader=FilesystemSourceReader(root=self._settings.base_dir / approved.reader.root),
            max_bytes=config.processing.max_source_bytes,
            max_entries=config.source_selection.max_listing_entries,
        )

    async def get_reference_pack(self, *, key: str, version: str) -> ReferencePack:
        """Load the exact approved catalog pack and dependency pins."""
        require_text(value=key, field="Pack key")
        require_text(value=version, field="Pack version")
        catalog = self._catalog()
        if catalog is None:
            raise ReferencePackNotFoundError
        return await catalog.get(key=key, version=version)

    async def list_reference_packs(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[ReferencePack]:
        """Page the exact available versions in the selected catalog."""
        if type(limit) is not int or limit < 1:
            raise ValueError("Use a positive catalog page size")
        catalog = self._catalog()
        if catalog is None:
            return Page(items=(), next_cursor=None)
        return await catalog.list(limit=limit, cursor=cursor)
