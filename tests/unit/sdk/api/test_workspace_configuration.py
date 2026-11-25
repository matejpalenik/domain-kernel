from __future__ import annotations

from typing import TYPE_CHECKING, override

import pytest
from pydantic import ValidationError

from domain_kernel import Client, ConfigurationError, ConfigurationSource, DatabaseInitialization
from domain_kernel._settings import load_settings
from domain_kernel.configuration import ClientConfiguration, Env, FilesystemReader, PostgreSQL
from domain_kernel.shared.application.inference import ModelGateway, ModelRequest, ModelResponse

if TYPE_CHECKING:
    from pathlib import Path


class _Gateway(ModelGateway):
    @override
    def __repr__(self) -> str:
        raise AssertionError("Gateway repr must never be called by configuration")

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        raise AssertionError("Configuration must never invoke the gateway")


def test_building_configuration_detaches_bindings_and_keeps_gateway() -> None:
    readers = [FilesystemReader(name="inputs", root=".")]
    gateway = _Gateway()
    options = ClientConfiguration(readers=readers, model_gateway=gateway)
    readers.clear()
    assert len(options.readers) == 1
    assert options.model_gateway is gateway
    assert "model_gateway" not in repr(options)
    assert "model_gateway" not in options.model_dump()
    for mode in ("validation", "serialization"):
        assert "model_gateway" not in str(options.model_json_schema(mode=mode))


def test_serialized_gateway_is_rejected_even_when_null() -> None:
    with pytest.raises(ValidationError):
        _ = ClientConfiguration.model_validate_json('{"model_gateway":null}')


def test_explicit_toml_loads_the_file_as_configuration_origin(tmp_path: Path) -> None:
    file = tmp_path / "deployment.toml"
    _ = file.write_text('[readers.legislation]\ntype = "filesystem"\nroot = "./legislation"\n')
    gateway = _Gateway()
    options = ClientConfiguration.from_toml(path=file, model_gateway=gateway)
    assert options.base_dir == tmp_path
    assert options.readers == (FilesystemReader(name="legislation", root="./legislation"),)
    assert options.model_gateway is gateway


def test_missing_explicit_toml_raises_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        _ = ClientConfiguration.from_toml(path=tmp_path / "missing.toml")


def test_client_inspection_preserves_file_origin_and_database_presence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "selected"
    folder.mkdir()
    config_path = folder / "domain-kernel.toml"
    _ = config_path.write_text('[database]\ntype = "sqlite"\n')
    options = ClientConfiguration.from_toml(path=config_path, model_gateway=_Gateway())
    started = Client(config=options)
    _ = config_path.write_text('invalid = "changed"')
    monkeypatch.chdir(tmp_path)
    report = started.inspect_configuration()
    assert report.source is ConfigurationSource.TOML
    assert report.source_path == config_path
    assert report.base_dir == folder
    assert report.database_initialization is DatabaseInitialization.EXPLICIT
    assert "model_gateway" in report.integrations
    assert not (folder / ".domain-kernel").exists()


def test_default_config_search_is_cwd_only_and_fails_for_existing_invalid_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = tmp_path / "child"
    child.mkdir()
    _ = (tmp_path / "domain-kernel.toml").write_text('bad = "in parent"')
    monkeypatch.chdir(child)
    assert Client().inspect_configuration().source is ConfigurationSource.DEFAULTS
    config_path = child / "domain-kernel.toml"
    config_path.mkdir()
    with pytest.raises(ConfigurationError):
        _ = Client()
    assert (
        Client(config=ClientConfiguration()).inspect_configuration().source
        is ConfigurationSource.PYTHON
    )
    config_path.rmdir()
    with pytest.raises(ConfigurationError):
        _ = ClientConfiguration.from_toml()
    _ = config_path.write_text('bad = "unknown setting"')
    with pytest.raises(ConfigurationError):
        _ = Client()


def test_explicit_environment_sources_and_safe_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "selected.env"
    _ = env_file.write_text("STATE_DSN=local-password\nUNRELATED=thing\n")
    config = ClientConfiguration(
        base_dir=tmp_path,
        env_file=env_file.name,
        database=PostgreSQL(dsn=Env(env="STATE_DSN")),
    )
    monkeypatch.setenv("STATE_DSN", "process-password")
    runtime = load_settings(config=config)
    assert runtime.secrets[0].value.get_secret_value() == "process-password"
    report = repr(Client(config=config).inspect_configuration())
    assert "STATE_DSN" not in report
    assert "process-password" not in report
    assert "local-password" not in report
    monkeypatch.delenv("STATE_DSN")
    selected = load_settings(config=config)
    assert selected.secrets[0].value.get_secret_value() == "local-password"

    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".env").write_text("STATE_DSN=implicit-password")
    automatic = ClientConfiguration(database=PostgreSQL(dsn=Env(env="STATE_DSN")))
    with pytest.raises(ConfigurationError, match="explicitly referenced"):
        _ = Client(config=automatic)


def test_toml_rejects_cross_provider_credential_binding(tmp_path: Path) -> None:
    path = tmp_path / "domain-kernel.toml"
    _ = path.write_text("""[credentials.s3]
provider = "aws_default_chain"
[readers.files]
type = "sharepoint"
drive_id = "drive"
root_item_id = "root"
credentials = "s3"
""")
    with pytest.raises(ConfigurationError, match="bindings"):
        _ = ClientConfiguration.from_toml(path=path)
