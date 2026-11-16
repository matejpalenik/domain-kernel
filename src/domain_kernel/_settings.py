"""Capture configuration origin, resolve deployment paths and read explicit secrets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, override

from dotenv import dotenv_values
from pydantic import Field, InstanceOf, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from domain_kernel._configuration_file import configuration_failure, discover_toml
from domain_kernel.configuration import (
    AwsStatic,
    ClientConfiguration,
    ConfigurationModel,
    Env,
    PostgreSQL,
    S3Reader,
    S3Store,
    SharePointReader,
)
from domain_kernel.diagnostics import ConfigurationSource

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from pydantic_settings import PydanticBaseSettingsSource


class ResolvedSecret(ConfigurationModel):
    """Private value of an explicitly referenced deployment setting."""

    reference: Env = Field(repr=False)
    value: SecretStr = Field(repr=False, exclude=True)


class RuntimeSettings(BaseSettings):
    """Effective startup settings after origin and explicit environment resolution."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
        hide_input_in_errors=True,
    )

    configuration: InstanceOf[ClientConfiguration]
    base_dir: Path
    configuration_source: ConfigurationSource
    configuration_path: Path | None
    database_explicit: bool
    secrets: tuple[ResolvedSecret, ...] = Field(default=(), repr=False, exclude=True)

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def _environment_references(*, configuration: ClientConfiguration) -> Iterable[Env]:
    if isinstance(configuration.database, PostgreSQL):
        yield configuration.database.dsn
    stores = (configuration.storage.artifact_store, *configuration.storage.additional_stores)
    for binding in (*configuration.readers, *stores):
        if isinstance(binding, SharePointReader):
            yield binding.credentials.client_secret
            for identifier in (binding.credentials.tenant_id, binding.credentials.client_id):
                if isinstance(identifier, Env):
                    yield identifier
        elif isinstance(binding, (S3Reader, S3Store)) and isinstance(
            binding.credentials, AwsStatic
        ):
            yield binding.credentials.access_key_id
            yield binding.credentials.secret_access_key
            if binding.credentials.session_token is not None:
                yield binding.credentials.session_token


def _resolve_env(
    *, configuration: ClientConfiguration, base_dir: Path
) -> tuple[ResolvedSecret, ...]:
    selected_file = configuration.env_file
    environment_file: Mapping[str, str | None] = {}
    if selected_file is not None:
        try:
            with (base_dir / selected_file).open(encoding="utf-8") as file:
                environment_file = dotenv_values(stream=file, interpolate=False)
        except (OSError, ValueError) as error:
            raise configuration_failure(
                path=("env_file",),
                message="Check access to the explicitly selected environment file",
            ) from error
    resolved: dict[str, ResolvedSecret] = {}
    for reference in _environment_references(configuration=configuration):
        if reference.env in resolved:
            continue
        value = os.environ.get(reference.env, environment_file.get(reference.env))
        if not value:
            raise configuration_failure(
                path=("environment",),
                message="Provide every explicitly referenced environment value",
            )
        resolved[reference.env] = ResolvedSecret(reference=reference, value=SecretStr(value))
    return tuple(resolved.values())


def load_settings(*, config: object) -> RuntimeSettings:
    """Capture one source without implicit settings merges or adapter I/O."""
    cwd = Path.cwd()
    source = ConfigurationSource.PYTHON
    if config is None:
        config = discover_toml(cwd=cwd)
        source = ConfigurationSource.DEFAULTS
    if config is None:
        options = ClientConfiguration(base_dir=cwd)
    elif isinstance(config, ClientConfiguration):
        options = config
    elif isinstance(config, (str, Path)):
        options = ClientConfiguration.from_toml(path=config)
    else:
        raise configuration_failure(
            path=("config",),
            message="Supply typed configuration or a TOML path",
        )
    path, database_explicit = options.configuration_origin()
    try:
        options = ClientConfiguration.model_validate(options)
    except ValidationError as error:
        raise configuration_failure(
            path=("config",),
            message="Check the values and bindings in the supplied configuration",
        ) from error
    base_dir = (cwd / options.base_dir).absolute()
    return RuntimeSettings(
        configuration=options,
        base_dir=base_dir,
        configuration_source=ConfigurationSource.TOML if path is not None else source,
        configuration_path=path,
        database_explicit=database_explicit,
        secrets=_resolve_env(configuration=options, base_dir=base_dir),
    )
