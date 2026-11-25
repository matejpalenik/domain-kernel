"""Bind workspace use cases and persistence at resource entry."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, final, override

from domain_kernel.configuration import (
    AwsStatic,
    Env,
    FilesystemReader,
    FilesystemStore,
    S3Reader,
    S3Store,
    SharePointReader,
    SQLite,
)
from domain_kernel.diagnostics import (
    ConfigurationReport,
    ConfigurationSetting,
    DatabaseInitialization,
)
from domain_kernel.modeling.application.dependencies import DependencyTransaction
from domain_kernel.modeling.application.exports import ExportDestination
from domain_kernel.modeling.application.validation_ports import SemanticValidator
from domain_kernel.reconciliation.application.ports import SimilarityScorer
from domain_kernel.reference_packs.application.selection_ports import PackSelectionTransaction
from domain_kernel.review.application.ports import ReviewTransaction
from domain_kernel.shared.application.artifacts import ArtifactStore
from domain_kernel.shared.application.catalogs import Models, Projects
from domain_kernel.shared.application.persistence import UnitOfWorkFactory
from domain_kernel.shared.errors import MissingCapabilityError
from domain_kernel.shared.validation import is_non_string_sequence, require_text, snapshot_sequence
from domain_kernel.sources.application.ports import (
    FormatParser,
    OriginalStore,
    ParsedSourceProvider,
    SourceReader,
)
from domain_kernel.sources.application.service import SourceRuntime
from domain_kernel.sources.domain.models import ProcessingLimits
from domain_kernel.sources.infrastructure.aws import AwsCredentialSnapshot, StaticAwsCredentials
from domain_kernel.sources.infrastructure.entra import EntraClientCredentials
from domain_kernel.sources.infrastructure.filesystem_reader import FilesystemSourceReader
from domain_kernel.sources.infrastructure.filesystem_store import (
    FilesystemArtifactStore,
    FilesystemOriginalStore,
)
from domain_kernel.sources.infrastructure.s3_reader import S3ReaderAdapter
from domain_kernel.sources.infrastructure.s3_store import S3ArtifactStore, S3OriginalStore
from domain_kernel.sources.infrastructure.sharepoint_reader import SharePointReaderAdapter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping, Sequence

    from pydantic import SecretStr

    from domain_kernel._settings import RuntimeSettings
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.application.catalogs import CatalogTransaction


@dataclass(frozen=True, kw_only=True)
class ClientIntegrations:
    """Caller-owned capabilities supplied to the client."""

    transactions: UnitOfWorkFactory[CatalogTransaction] | None = None
    parsed_source_providers: Sequence[ParsedSourceProvider] = ()
    validators: Sequence[SemanticValidator] = ()
    source_readers: Mapping[str, SourceReader] = field(default_factory=dict[str, SourceReader])
    format_parsers: Mapping[str, FormatParser] = field(default_factory=dict[str, FormatParser])
    original_stores: Mapping[str, OriginalStore] = field(default_factory=dict[str, OriginalStore])
    artifact_stores: Mapping[str, ArtifactStore] = field(default_factory=dict[str, ArtifactStore])
    similarity_scorer: SimilarityScorer | None = None

    def __post_init__(self) -> None:
        """Require a callable resource factory when configured."""
        if self.transactions is not None and not callable(self.transactions):
            raise TypeError("Supply a callable transaction resource factory")
        _check_similarity_scorer(value=self.similarity_scorer)

        validators = _freeze_validators(values=self.validators)
        identities = tuple(item.fingerprint for item in validators)
        for fingerprint in identities:
            require_text(value=fingerprint, field="Validator fingerprint")
        if len(set(identities)) != len(identities):
            raise ValueError("Select one required validator per fingerprint")
        object.__setattr__(self, "validators", validators)

        providers = snapshot_sequence(
            items=self.parsed_source_providers,
            item_type=ParsedSourceProvider,
            field="Parsed source providers",
        )
        if len({provider.name for provider in providers}) != len(providers):
            raise ValueError("Register distinct parsed source provider names")
        object.__setattr__(self, "parsed_source_providers", providers)
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

        object.__setattr__(
            self,
            "artifact_stores",
            _freeze_capabilities(values=self.artifact_stores, kind=ArtifactStore),
        )


def _check_similarity_scorer(*, value: object) -> None:
    if value is not None and (
        isinstance(value, type)
        or not isinstance(value, SimilarityScorer)
        or not callable(value.score)
    ):
        raise TypeError("Supply a similarity scorer instance")


def _freeze_validators(*, values: Sequence[object]) -> tuple[SemanticValidator, ...]:
    if not is_non_string_sequence(values):
        raise TypeError("Supply a sequence of compatible semantic validators")
    result: list[SemanticValidator] = []
    for value in values:
        if not isinstance(value, SemanticValidator):
            raise TypeError("Supply a compatible semantic validator")
        result.append(value)
    return tuple(result)


def _freeze_capabilities[T](*, values: Mapping[str, object], kind: type[T]) -> Mapping[str, T]:
    captured: dict[str, T] = {}
    for name, value in values.items():
        if type(name) is not str or not name.strip() or not isinstance(value, kind):
            raise TypeError("Supply exact names and compatible source capabilities")
        captured[name] = value
    return MappingProxyType(captured)


def _secret(*, settings: RuntimeSettings, reference: Env) -> SecretStr:
    for value in settings.secrets:
        if value.reference == reference:
            return value.value
    raise MissingCapabilityError(message="Resolve the explicitly configured credential reference.")


def _aws_credentials(
    *, settings: RuntimeSettings, binding: S3Reader | S3Store
) -> StaticAwsCredentials | None:
    config = binding.credentials
    if not isinstance(config, AwsStatic):
        return None
    return StaticAwsCredentials(
        snapshot=AwsCredentialSnapshot(
            access_key_id=_secret(settings=settings, reference=config.access_key_id),
            secret_access_key=_secret(settings=settings, reference=config.secret_access_key),
            session_token=None
            if config.session_token is None
            else _secret(settings=settings, reference=config.session_token),
        )
    )


def _reader(
    *, settings: RuntimeSettings, item: FilesystemReader | S3Reader | SharePointReader
) -> SourceReader:
    if isinstance(item, FilesystemReader):
        return FilesystemSourceReader(root=settings.base_dir / item.root, name=item.name)
    if isinstance(item, S3Reader):
        return S3ReaderAdapter(
            config=item, credentials=_aws_credentials(settings=settings, binding=item)
        )
    credential = item.credentials
    tenant = credential.tenant_id
    client = credential.client_id
    return SharePointReaderAdapter(
        config=item,
        credentials=EntraClientCredentials(
            tenant_id=_secret(settings=settings, reference=tenant).get_secret_value()
            if isinstance(tenant, Env)
            else tenant,
            client_id=_secret(settings=settings, reference=client).get_secret_value()
            if isinstance(client, Env)
            else client,
            client_secret=_secret(settings=settings, reference=credential.client_secret),
        ),
    )


def source_runtime(*, settings: RuntimeSettings, integrations: ClientIntegrations) -> SourceRuntime:
    """Bind configured and caller-owned source capabilities once per client."""
    config = settings.configuration
    readers: dict[str, SourceReader] = {
        item.name: _reader(settings=settings, item=item)
        for item in config.readers
        if item.name not in integrations.source_readers
    }
    readers.update(integrations.source_readers)
    stores: dict[str, OriginalStore] = {
        item.name: (
            FilesystemOriginalStore(root=settings.base_dir / item.root, name=item.name)
            if isinstance(item, FilesystemStore)
            else S3OriginalStore(
                config=item, credentials=_aws_credentials(settings=settings, binding=item)
            )
        )
        for item in (config.storage.artifact_store, *config.storage.additional_stores)
        if item.name not in integrations.original_stores
    }
    stores.update(integrations.original_stores)
    parsers = dict(integrations.format_parsers)
    if (documents := config.parsers.documents) is not None:
        from domain_kernel.sources.infrastructure.docling_documents import (  # noqa: PLC0415 - Opt-in adapter.
            DoclingParser,
        )

        parser = DoclingParser.for_discovery(
            chunking="hierarchical",
            artifacts_path=(
                settings.base_dir / documents.artifacts_path if documents.artifacts_path else None
            ),
            ocr=documents.ocr,
            asr_model_path=(
                settings.base_dir / documents.asr_model_path if documents.asr_model_path else None
            ),
            xbrl_taxonomy_path=(
                settings.base_dir / documents.xbrl_taxonomy_path
                if documents.xbrl_taxonomy_path
                else None
            ),
        )
        for name in ("pdf", "word", "excel", "csv", "document"):
            _ = parsers.setdefault(name, parser)
    return SourceRuntime(
        readers=readers,
        parsers=parsers,
        stores=stores,
        limits=ProcessingLimits(
            max_source_bytes=config.processing.max_source_bytes,
            max_concurrent_sources=config.processing.max_concurrent_sources,
            max_expanded_bytes=config.processing.max_expanded_bytes,
            max_pages=config.processing.max_pages,
            max_table_cells=config.processing.max_table_cells,
            max_tables=config.processing.max_tables,
        ),
        parsed_providers={
            provider.name: provider.resolver for provider in integrations.parsed_source_providers
        },
        retain_parsed=config.retention.extracted_text,
        retain_excerpts=config.retention.evidence_excerpts,
        selection=config.source_selection,
        default_original_store=config.storage.artifact_store.name
        if config.retention.originals
        else None,
    )


def artifact_destinations(
    *, settings: RuntimeSettings, integrations: ClientIntegrations
) -> Mapping[str, ExportDestination]:
    """Bind approved artifact destinations for workspace handles."""
    config = settings.configuration.storage
    stores: dict[str, ExportDestination] = {}
    for item in (config.artifact_store, *config.additional_stores):
        if item.name not in integrations.artifact_stores:
            store = (
                FilesystemArtifactStore(root=settings.base_dir / item.root, name=item.name)
                if isinstance(item, FilesystemStore)
                else S3ArtifactStore(
                    config=item, credentials=_aws_credentials(settings=settings, binding=item)
                )
            )
            stores[item.name] = ExportDestination(store=store, binding=store.provider_scope)
    stores.update(
        (name, ExportDestination(store=store, binding=f"host:{name}"))
        for name, store in integrations.artifact_stores.items()
    )
    return MappingProxyType(stores)


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
        from domain_kernel._database import (  # noqa: PLC0415 - load only during database use
            PostgreSQLSettings,
            PostgreSQLUnitOfWorkFactory,
            SQLiteSettings,
            SQLiteUnitOfWorkFactory,
        )

        if not isinstance(database, SQLite):
            return PostgreSQLUnitOfWorkFactory(
                settings=PostgreSQLSettings(
                    dsn=_secret(settings=self._settings, reference=database.dsn).get_secret_value(),
                    schema=database.schema_name,
                )
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
