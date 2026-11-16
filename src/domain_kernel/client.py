"""Python SDK entry point for configuration and workspace selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from domain_kernel._composition import (
    ClientIntegrations,
    configuration_report,
    open_projects,
    transaction_resources,
)
from domain_kernel._settings import load_settings
from domain_kernel.modeling.domain.snapshots import PublicationRules
from domain_kernel.project import Project

if TYPE_CHECKING:
    from domain_kernel.configuration import ConfigurationInput
    from domain_kernel.diagnostics import ConfigurationReport
    from domain_kernel.projects.domain.project_info import ProjectInfo
    from domain_kernel.shared.contracts import Page
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
            info=info, resources=self._resources, publication_rules=self._publication_rules
        )

    async def get_project(self, *, name: str) -> Project:
        """Open an existing project by exact name."""
        async with open_projects(resources=self._resources) as projects:
            info = await projects.get(name=name)
        return Project(
            info=info, resources=self._resources, publication_rules=self._publication_rules
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
