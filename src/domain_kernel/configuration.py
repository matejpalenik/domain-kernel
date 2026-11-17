"""Typed SDK configuration and environment references."""

from __future__ import annotations

from collections.abc import Sequence  # noqa: TC003 - Pydantic resolves field types at runtime.
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
    PrivateAttr,
    StrictBool,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema  # noqa: TC002 - Runtime schema metadata.

from domain_kernel._configuration_file import configuration_failure, distinct_names, load_toml
from domain_kernel._shared.application.inference import ModelGateway

type PositiveInt = Annotated[int, Field(strict=True, gt=0)]
type NonEmpty = Annotated[str, StringConstraints(pattern=r"\S")]


class ConfigurationModel(BaseModel):
    """Base for immutable, strictly validated settings."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
        revalidate_instances="always",
        hide_input_in_errors=True,
    )

    @field_validator("root", "path", "base_dir", "env_file", check_fields=False)
    @classmethod
    def _check_path(cls, value: str | Path | None) -> str | Path | None:
        if value is not None and (not str(value).strip() or "\x00" in str(value)):
            raise ValueError("Supply a valid settings path")
        return value


class Env(ConfigurationModel):
    """Reference an explicitly selected environment variable."""

    env: NonEmpty

    @field_validator("env")
    @classmethod
    def _check_key(cls, value: str) -> str:
        if "\x00" in value or "=" in value:
            raise ValueError("Supply a valid environment variable name")
        return value


class SQLite(ConfigurationModel):
    """Select an operator-managed SQLite database."""

    type: Literal["sqlite"] = "sqlite"
    path: str | Path = ".domain-kernel/state.sqlite3"


class PostgreSQL(ConfigurationModel):
    """Select a PostgreSQL connection supplied by the deployment."""

    type: Literal["postgresql"] = "postgresql"
    dsn: Env
    schema_name: NonEmpty = "domain_kernel"


type DatabaseConfiguration = Annotated[SQLite | PostgreSQL, Field(discriminator="type")]


class AwsProfile(ConfigurationModel):
    """Configure aws profile."""

    provider: Literal["aws_profile"] = "aws_profile"
    profile: NonEmpty


class AwsDefaultChain(ConfigurationModel):
    """Configure aws default chain."""

    provider: Literal["aws_default_chain"] = "aws_default_chain"


class AwsStatic(ConfigurationModel):
    """Configure aws static."""

    provider: Literal["aws_static"] = "aws_static"
    access_key_id: Env
    secret_access_key: Env
    session_token: Env | None = None


type AwsCredentials = Annotated[
    AwsProfile | AwsDefaultChain | AwsStatic,
    Field(discriminator="provider"),
]


class EntraClientSecret(ConfigurationModel):
    """Configure entra client secret."""

    provider: Literal["entra_client_secret"] = "entra_client_secret"
    tenant_id: str | Env
    client_id: str | Env
    client_secret: Env


class FilesystemReader(ConfigurationModel):
    """Configure filesystem reader."""

    type: Literal["filesystem"] = "filesystem"
    name: NonEmpty
    root: str | Path


class S3Reader(ConfigurationModel):
    """Configure s3 reader."""

    type: Literal["s3"] = "s3"
    name: NonEmpty
    bucket: NonEmpty
    prefix: str = ""
    region: str | None = None
    credentials: AwsCredentials


class SharePointReader(ConfigurationModel):
    """Configure share point reader."""

    type: Literal["sharepoint"] = "sharepoint"
    name: NonEmpty
    drive_id: NonEmpty
    root_item_id: NonEmpty
    credentials: EntraClientSecret


type ReaderConfiguration = Annotated[
    FilesystemReader | S3Reader | SharePointReader,
    Field(discriminator="type"),
]


class FilesystemStore(ConfigurationModel):
    """Configure filesystem store."""

    type: Literal["filesystem"] = "filesystem"
    name: NonEmpty
    root: str | Path


class S3Store(ConfigurationModel):
    """Configure s3 store."""

    type: Literal["s3"] = "s3"
    name: NonEmpty
    bucket: NonEmpty
    prefix: str = ""
    region: str | None = None
    credentials: AwsCredentials


type StoreConfiguration = Annotated[FilesystemStore | S3Store, Field(discriminator="type")]


class OpenpyxlParser(ConfigurationModel):
    """Configure openpyxl parser."""

    type: Literal["openpyxl"] = "openpyxl"


class DoclingParser(ConfigurationModel):
    """Configure docling parser."""

    type: Literal["docling"] = "docling"


class DuckDBParser(ConfigurationModel):
    """Configure duck d b parser."""

    type: Literal["duckdb"] = "duckdb"


class RdfLibParser(ConfigurationModel):
    """Configure rdf lib parser."""

    type: Literal["rdflib"] = "rdflib"


class Parsers(ConfigurationModel):
    """Configure parsers."""

    excel: OpenpyxlParser | None = None
    documents: DoclingParser | None = None
    csv: DuckDBParser | None = None
    ontology: RdfLibParser | None = None


class Storage(ConfigurationModel):
    """Configure storage."""

    artifact_store: StoreConfiguration = Field(
        default_factory=lambda: FilesystemStore(name="artifacts", root=".domain-kernel/artifacts"),
    )
    additional_stores: Sequence[StoreConfiguration] = ()

    @field_validator("additional_stores")
    @classmethod
    def _freeze_stores(cls, value: Sequence[StoreConfiguration]) -> tuple[StoreConfiguration, ...]:
        return tuple(value)

    @model_validator(mode="after")
    def _unique_stores(self) -> Self:
        names = (store.name for store in (self.artifact_store, *self.additional_stores))
        distinct_names(names=names, category="store")
        return self


class InMemoryProcessing(ConfigurationModel):
    """Configure in memory processing."""

    mode: Literal["memory"] = "memory"
    max_source_bytes: PositiveInt = 64 * 1024 * 1024
    max_concurrent_sources: PositiveInt = 2
    max_expanded_bytes: PositiveInt = 256 * 1024 * 1024
    max_pages: PositiveInt = 1000
    max_table_cells: PositiveInt = 1_000_000
    max_tables: PositiveInt = 128


class Retention(ConfigurationModel):
    """Configure retention."""

    originals: StrictBool = False
    extracted_text: StrictBool = False
    evidence_excerpts: StrictBool = False


class SourceSelectionLimits(ConfigurationModel):
    """Configure source selection limits."""

    max_files: PositiveInt = 1000
    max_listing_entries: PositiveInt = 10000
    max_listing_depth: PositiveInt = 32
    listing_timeout_seconds: PositiveInt = 60


class InferencePolicy(ConfigurationModel):
    """Configure inference policy."""

    timeout_seconds: Annotated[float, Field(gt=0)] = 60.0
    max_attempts: PositiveInt = 3
    max_input_bytes: PositiveInt = 2 * 1024 * 1024
    max_output_bytes: PositiveInt = 128 * 1024
    max_proposals: PositiveInt = 64


class PublicationPolicy(ConfigurationModel):
    """Configure publication policy."""

    allow_reviewed_nonblocking_questions: StrictBool = True


class ReferencePackCatalog(ConfigurationModel):
    """Configure reference pack catalog."""

    reader: ReaderConfiguration  # Direct typed approved reader; no public fallback.


class ClientConfiguration(ConfigurationModel):
    """Configure the SDK while retaining host-owned runtime integrations."""

    schema_version: Literal[1] = 1
    base_dir: str | Path = Field(default_factory=Path.cwd)
    env_file: str | Path | None = None
    database: DatabaseConfiguration = Field(default_factory=SQLite)
    readers: Sequence[ReaderConfiguration] = Field(
        default_factory=lambda: (FilesystemReader(name="inputs", root="."),),
    )
    reference_packs: ReferencePackCatalog | None = None
    parsers: Parsers = Field(default_factory=Parsers)
    storage: Storage = Field(default_factory=Storage)
    processing: InMemoryProcessing = Field(default_factory=InMemoryProcessing)
    source_selection: SourceSelectionLimits = Field(default_factory=SourceSelectionLimits)
    retention: Retention = Field(default_factory=Retention)
    inference: InferencePolicy = Field(default_factory=InferencePolicy)
    model_gateway: SkipJsonSchema[InstanceOf[ModelGateway] | None] = Field(
        default=None,
        repr=False,
        exclude=True,
    )
    publication: PublicationPolicy = Field(default_factory=PublicationPolicy)

    _toml_path: Path | None = PrivateAttr(default=None)
    _database_explicit: bool = PrivateAttr(default=False)

    @model_validator(mode="before")
    @classmethod
    def _reject_serialized_gateway(cls, data: object, info: ValidationInfo) -> object:
        supplied: object = data
        if info.mode == "json" and isinstance(data, dict) and "model_gateway" in data:
            raise ValueError("Supply the gateway as a Python object")
        return supplied

    @field_validator("model_gateway", mode="before")
    @classmethod
    def _check_gateway(cls, value: object) -> object:
        if value is not None and (
            isinstance(value, type)
            or not isinstance(value, ModelGateway)
            or not callable(value.generate)
        ):
            raise ValueError("Supply a ModelGateway instance")
        return value

    @field_validator("readers")
    @classmethod
    def _freeze_readers(
        cls, value: Sequence[ReaderConfiguration]
    ) -> tuple[ReaderConfiguration, ...]:
        return tuple(value)

    @model_validator(mode="after")
    def _check_bindings(self) -> Self:
        self._database_explicit = "database" in self.model_fields_set
        distinct_names(names=(reader.name for reader in self.readers), category="reader")
        if self.reference_packs is not None and self.reference_packs.reader not in self.readers:
            raise ValueError("Use a registered reader in the reference pack catalog")
        return self

    @classmethod
    def from_toml(
        cls,
        *,
        path: str | Path = "domain-kernel.toml",
        model_gateway: ModelGateway | None = None,
    ) -> Self:
        """Read a selected TOML configuration file."""
        selected, data = load_toml(
            path=path,
            validate_credentials=TypeAdapter(AwsCredentials | EntraClientSecret).validate_python,
            validate_store=TypeAdapter(StoreConfiguration).validate_python,
        )
        if model_gateway is not None:
            data["model_gateway"] = model_gateway
        try:
            configuration = cls.model_validate(data)
        except ValidationError as error:
            raise configuration_failure(
                path=("config",),
                message="Check the values and bindings in the selected configuration",
            ) from error
        configuration._toml_path = selected  # noqa: SLF001 - Capture this instance's origin.
        return configuration

    def configuration_origin(self) -> tuple[Path | None, bool]:
        """Return the source path and original database field presence."""
        return self._toml_path, self._database_explicit


type ConfigurationInput = str | Path | ClientConfiguration
