"""Read one TOML configuration and resolve its named binding references."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from domain_kernel.configuration_error import ConfigurationError
from domain_kernel.shared.diagnostics.issue import Issue

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

_TABLE = TypeAdapter(dict[str, object])
_TABLES = TypeAdapter(dict[str, dict[str, object]])
_NAMES = TypeAdapter(list[str])
_DEFAULT_PATH = "domain-kernel.toml"


def configuration_failure(*, path: tuple[str | int, ...], message: str) -> ConfigurationError:
    """Build a diagnostic from an allowlisted location and message."""
    return ConfigurationError(
        issues=[Issue(code="invalid_configuration", path=path, message=message)]
    )


def _binding(
    *,
    items: dict[str, dict[str, object]],
    reference: object,
    category: str,
) -> dict[str, object]:
    if type(reference) is not str or reference not in items:
        message = f"Select an existing {category} binding"
        raise configuration_failure(path=(category,), message=message)
    return items[reference]


def _named_bindings(
    *,
    data: object,
    credentials: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    items = _TABLES.validate_python(data, strict=True)
    result: dict[str, dict[str, object]] = {}
    for name, binding in items.items():
        if "name" in binding:
            raise configuration_failure(
                path=("name",), message="Use the TOML table name for a binding"
            )
        options = {**binding, "name": name}
        if isinstance(reference := options.get("credentials"), str):
            options["credentials"] = _binding(
                items=credentials,
                reference=reference,
                category="credentials",
            )
        result[name] = options
    return result


def _normalize(
    *,
    data: dict[str, object],
    validate_credentials: Callable[[object], object],
    validate_store: Callable[[object], object],
) -> None:
    credentials = _TABLES.validate_python(data.pop("credentials", {}), strict=True)
    for credential in credentials.values():
        _ = validate_credentials(credential)
    readers: dict[str, dict[str, object]]
    if "readers" in data:
        readers = _named_bindings(data=data["readers"], credentials=credentials)
        data["readers"] = tuple(readers.values())
    else:
        readers = {"inputs": {"type": "filesystem", "name": "inputs", "root": "."}}
    if "reference_packs" in data:
        catalog = _TABLE.validate_python(data["reference_packs"], strict=True)
        catalog["reader"] = _binding(
            items=readers, reference=catalog.get("reader"), category="reader"
        )
        data["reference_packs"] = catalog
    stores = _named_bindings(data=data.pop("stores", {}), credentials=credentials)
    for store in stores.values():
        _ = validate_store(store)
    if "storage" in data:
        storage = _TABLE.validate_python(data["storage"], strict=True)
        if "artifact_store" in storage:
            storage["artifact_store"] = _binding(
                items=stores,
                reference=storage["artifact_store"],
                category="store",
            )
        if "additional_stores" in storage:
            names = _NAMES.validate_python(storage["additional_stores"], strict=True)
            storage["additional_stores"] = tuple(
                _binding(items=stores, reference=name, category="store") for name in names
            )
        data["storage"] = storage


def load_toml(
    *,
    path: str | Path,
    validate_credentials: Callable[[object], object],
    validate_store: Callable[[object], object],
) -> tuple[Path, dict[str, object]]:
    """Read the selected file and prepare typed-model input."""
    try:
        selected = Path(path).absolute()
        if not selected.is_file():
            raise configuration_failure(
                path=("config",),
                message="Select an existing Domain Kernel TOML file",
            )
        with selected.open(mode="rb") as file:
            data: dict[str, object] = tomllib.load(file)
        if "model_gateway" in data:
            raise configuration_failure(
                path=("model_gateway",),
                message="Supply the gateway as a Python object",
            )
        _normalize(
            data=data, validate_credentials=validate_credentials, validate_store=validate_store
        )
        base_dir = data.get("base_dir", ".")
        if type(base_dir) is not str or not base_dir.strip() or "\x00" in base_dir:
            raise configuration_failure(path=("base_dir",), message="Supply a valid base directory")
        data["base_dir"] = (selected.parent / base_dir).absolute()
    except (OSError, ValueError) as error:
        raise configuration_failure(
            path=("config",),
            message="Read a valid Domain Kernel TOML configuration file",
        ) from error
    return selected, data


def discover_toml(*, cwd: Path) -> Path | None:
    """Look for the conventionally named file in the captured working directory."""
    path = cwd / _DEFAULT_PATH
    try:
        _ = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise configuration_failure(
            path=("config",),
            message="Check access to the selected configuration file",
        ) from error
    return path


def distinct_names(*, names: Iterable[str], category: str) -> None:
    """Require a single binding per public lookup name."""
    snapshot = tuple(names)
    if len(snapshot) != len(set(snapshot)):
        message = f"Choose distinct {category} binding names"
        raise ValueError(message)
