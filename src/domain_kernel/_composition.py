"""Bind workspace use cases and persistence at resource entry."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, final, override

from domain_kernel._shared.application.catalogs import Models, Projects
from domain_kernel._shared.application.persistence import UnitOfWorkFactory
from domain_kernel.configuration import FilesystemReader, FilesystemStore, SQLite
from domain_kernel.diagnostics import (
    ConfigurationReport,
    ConfigurationSetting,
    DatabaseInitialization,
)
from domain_kernel.modeling.application.dependencies import DependencyTransaction
from domain_kernel.reference_packs.application.selection_ports import PackSelectionTransaction
from domain_kernel.review.application.ports import ReviewTransaction
from domain_kernel.shared.errors import MissingCapabilityError
from domain_kernel.sources.application.ports import FormatParser, OriginalStore, SourceReader
from domain_kernel.sources.application.service import SourceRuntime
from domain_kernel.sources.domain.models import ProcessingLimits
from domain_kernel.sources.infrastructure.filesystem_reader import FilesystemSourceReader
from domain_kernel.sources.infrastructure.filesystem_store import FilesystemArtifactStore

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping

    from domain_kernel._settings import RuntimeSettings
    from domain_kernel._shared.application.catalogs import CatalogTransaction
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId


@dataclass(frozen=True, kw_only=True)
class ClientIntegrations:
    """Caller-owned capabilities supplied to the client."""

    transactions: UnitOfWorkFactory[CatalogTransaction] | None = None
    source_readers: Mapping[str, SourceReader] = field(default_factory=dict[str, SourceReader])
    format_parsers: Mapping[str, FormatParser] = field(default_factory=dict[str, FormatParser])
    original_stores: Mapping[str, OriginalStore] = field(default_factory=dict[str, OriginalStore])

    def __post_init__(self) -> None:
        """Require a callable resource factory when configured."""
        if self.transactions is not None and not callable(self.transactions):
            raise TypeError("Supply a callable transaction resource factory")

        object.__setattr__(
            self,
            "source_readers",
            _freeze_capabilities(values=self.source_readers, kind=SourceReader),
        )
        object.__setattr__(
            self,
            "format_parsers",
            _freeze_capabilities(values=self.format_parsers, kind=FormatParser),
        )
        object.__setattr__(
            self,
            "original_stores",
            _freeze_capabilities(values=self.original_stores, kind=OriginalStore),
        )


def _freeze_capabilities[T](*, values: Mapping[str, object], kind: type[T]) -> Mapping[str, T]:
    captured: dict[str, T] = {}
    for name, value in values.items():
        if type(name) is not str or not name.strip() or not isinstance(value, kind):
            raise TypeError("Supply exact names and compatible source capabilities")
        captured[name] = value
    return MappingProxyType(captured)


def source_runtime(*, settings: RuntimeSettings, integrations: ClientIntegrations) -> SourceRuntime:
    """Bind local readers and host-supplied source capabilities once per client."""
    config = settings.configuration
    readers: dict[str, SourceReader] = {
        item.name: FilesystemSourceReader(root=settings.base_dir / item.root, name=item.name)
        for item in config.readers
        if isinstance(item, FilesystemReader)
    }
    readers.update(integrations.source_readers)
    stores: dict[str, OriginalStore] = {
        item.name: FilesystemArtifactStore(root=settings.base_dir / item.root, name=item.name)
        for item in (config.storage.artifact_store, *config.storage.additional_stores)
        if isinstance(item, FilesystemStore)
    }
    stores.update(integrations.original_stores)
    return SourceRuntime(
        readers=readers,
        parsers=integrations.format_parsers,
        stores=stores,
        limits=ProcessingLimits(
            max_source_bytes=config.processing.max_source_bytes,
            max_concurrent_sources=config.processing.max_concurrent_sources,
            max_expanded_bytes=config.processing.max_expanded_bytes,
            max_pages=config.processing.max_pages,
        ),
        selection=config.source_selection,
        default_original_store=config.storage.artifact_store.name
        if config.retention.originals
        else None,
    )


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
            baseline_definitions=transaction.definitions
            if isinstance(transaction, ReviewTransaction)
            else None,
            resolver=transaction.dependencies
            if isinstance(transaction, DependencyTransaction)
            else None,
            audit=transaction.audit,
            transaction=transaction,
        )
