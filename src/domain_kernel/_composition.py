"""Bind workspace use cases and persistence at resource entry."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, final, override

from domain_kernel._shared.application.catalogs import Models, Projects
from domain_kernel._shared.application.persistence import UnitOfWorkFactory
from domain_kernel.configuration import SQLite
from domain_kernel.diagnostics import (
    ConfigurationReport,
    ConfigurationSetting,
    DatabaseInitialization,
)
from domain_kernel.modeling.application.dependencies import DependencyTransaction
from domain_kernel.reference_packs.application.selection_ports import PackSelectionTransaction
from domain_kernel.shared.errors import MissingCapabilityError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from domain_kernel._settings import RuntimeSettings
    from domain_kernel._shared.application.catalogs import CatalogTransaction
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId


@dataclass(frozen=True, kw_only=True)
class ClientIntegrations:
    """Caller-owned capabilities supplied to the client."""

    transactions: UnitOfWorkFactory[CatalogTransaction] | None = None

    def __post_init__(self) -> None:
        """Require a callable resource factory when configured."""
        if self.transactions is not None and not callable(self.transactions):
            raise TypeError("Supply a callable transaction resource factory")


@final
class _ConfiguredTransactions(UnitOfWorkFactory["CatalogTransaction"]):
    def __init__(self, *, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._resources: UnitOfWorkFactory[CatalogTransaction] | None = None

    @override
    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[CatalogTransaction]:
        if self._resources is None:
            self._resources = self._select()
        async with self._resources() as transaction:
            yield transaction

    def _select(self) -> UnitOfWorkFactory[CatalogTransaction]:
        database = self._settings.configuration.database
        if not isinstance(database, SQLite):
            raise MissingCapabilityError(message="Configure a PostgreSQL transaction provider")
        from domain_kernel._database import (  # noqa: PLC0415 - load only during database use
            SQLiteSettings,
            SQLiteUnitOfWorkFactory,
        )

        return SQLiteUnitOfWorkFactory(
            settings=SQLiteSettings(
                path=self._settings.base_dir / database.path,
                initialize_on_first_use=not self._settings.database_explicit,
            )
        )


def transaction_resources(
    *,
    settings: RuntimeSettings,
    integrations: ClientIntegrations,
) -> UnitOfWorkFactory[CatalogTransaction]:
    """Select host-managed or lazily acquired built-in persistence."""
    if integrations.transactions is not None:
        return integrations.transactions
    return _ConfiguredTransactions(settings=settings)


def configuration_report(
    *,
    settings: RuntimeSettings,
    integrations: ClientIntegrations,
) -> ConfigurationReport:
    """Capture allowlisted settings without probing any configured capability."""
    config = settings.configuration
    if integrations.transactions is not None:
        mode = DatabaseInitialization.HOST_MANAGED
    elif settings.database_explicit:
        mode = DatabaseInitialization.EXPLICIT
    else:
        mode = DatabaseInitialization.AUTOMATIC
    enabled: list[str] = []
    if integrations.transactions is not None:
        enabled.append("transactions")
    if config.model_gateway is not None:
        enabled.append("model_gateway")
    return ConfigurationReport(
        source=settings.configuration_source,
        source_path=settings.configuration_path,
        base_dir=settings.base_dir,
        database_initialization=mode,
        integrations=tuple(enabled),
        settings=(
            ConfigurationSetting(path=("database", "type"), value=config.database.type),
            ConfigurationSetting(
                path=("readers",),
                value=", ".join(reader.name for reader in config.readers),
            ),
            ConfigurationSetting(
                path=("storage", "artifact_store"), value=config.storage.artifact_store.name
            ),
            ConfigurationSetting(
                path=("source_selection", "max_files"),
                value=str(config.source_selection.max_files),
            ),
        ),
    )


@asynccontextmanager
async def open_projects(
    *,
    resources: UnitOfWorkFactory[CatalogTransaction],
) -> AsyncGenerator[Projects]:
    """Inject resources from a fresh context into the project use cases."""
    async with resources() as transaction:
        yield Projects(
            catalog=transaction.projects,
            audit=transaction.audit,
            transaction=transaction,
        )


@asynccontextmanager
async def open_models(
    *,
    resources: UnitOfWorkFactory[CatalogTransaction],
    project_id: ProjectId,
) -> AsyncGenerator[Models]:
    """Inject resources from a fresh context into the scoped model use cases."""
    async with resources() as transaction:
        yield Models(
            project_id=project_id,
            catalog=transaction.models,
            packs=transaction.packs if isinstance(transaction, PackSelectionTransaction) else None,
            resolver=transaction.dependencies
            if isinstance(transaction, DependencyTransaction)
            else None,
            audit=transaction.audit,
            transaction=transaction,
        )
