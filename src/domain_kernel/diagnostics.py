"""Redacted, detached inspection of captured client settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@unique
class ConfigurationSource(StrEnum):
    """Origin of the captured settings."""

    DEFAULTS = "defaults"
    PYTHON = "python"
    TOML = "toml"


@unique
class DatabaseInitialization(StrEnum):
    """Owner of schema preparation for the selected persistence capability."""

    AUTOMATIC = "automatic"
    EXPLICIT = "explicit"
    HOST_MANAGED = "host_managed"


@dataclass(frozen=True, kw_only=True)
class ConfigurationSetting:
    """A redacted display value and its setting path."""

    path: tuple[str, ...]
    value: str


@dataclass(frozen=True, kw_only=True)
class ConfigurationReport:
    """Safe configuration snapshot for inspection."""

    source: ConfigurationSource
    source_path: Path | None
    base_dir: Path
    database_initialization: DatabaseInitialization
    settings: tuple[ConfigurationSetting, ...]
    integrations: tuple[str, ...]
