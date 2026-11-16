"""Compose the built-in SQLite resources and operator-owned schema setup."""

from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override

from domain_kernel._shared.application.persistence import UnitOfWorkFactory
from domain_kernel._shared.infrastructure.sqlite import (
    DatabaseSchemaError,
    create_engine,
    finish,
    open_operation,
    prepare_schema,
    upgrade_schema,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from domain_kernel._shared.application.persistence import Clock
    from domain_kernel._shared.infrastructure.sqlite import SQLiteTransaction

__all__ = ["DatabaseSchemaError", "SQLiteSettings", "SQLiteUnitOfWorkFactory", "SchemaManager"]


@dataclass(frozen=True, kw_only=True)
class SQLiteSettings:
    """Effective internal SQLite settings selected by composition."""

    path: Path
    initialize_on_first_use: bool = False
    busy_timeout: float = 5.0
    concurrency: int = 4

    def __post_init__(self) -> None:
        """Capture a fixed absolute path and validate resource limits."""
        if type(self.initialize_on_first_use) is not bool:
            raise TypeError("SQLite initialization selection must be a bool")
        if type(self.busy_timeout) not in (int, float) or not math.isfinite(self.busy_timeout):
            raise ValueError("SQLite busy timeout must be a finite number")
        if self.busy_timeout <= 0:
            raise ValueError("SQLite busy timeout must be positive")
        if type(self.concurrency) is not int or self.concurrency < 1:
            raise ValueError("SQLite operation concurrency must be a positive integer")
        object.__setattr__(self, "path", self.path.absolute())


@final
class SchemaManager:
    """Prepare the exact configured SQLite file under an exclusive bootstrap gate."""

    def __init__(self, *, settings: SQLiteSettings) -> None:
        """Retain configuration without touching the filesystem."""
        self._settings = settings

    async def initialize(self) -> None:
        """Create a new schema, or confirm the existing schema can be reused."""
        try:
            await finish(
                asyncio.to_thread(self._settings.path.parent.mkdir, parents=True, exist_ok=True)
            )
        except OSError:
            raise DatabaseSchemaError(
                message="Check access to the selected SQLite directory"
            ) from None
        engine = create_engine(
            path=self._settings.path, timeout=self._settings.busy_timeout, create=True
        )
        try:
            await finish(prepare_schema(engine=engine, initialize=True))
        finally:
            await finish(engine.dispose())

    async def upgrade(self, *, target_version: str) -> None:
        """Upgrade the exact selected workspace after an explicit operator request."""
        engine = create_engine(
            path=self._settings.path,
            timeout=self._settings.busy_timeout,
            create=False,
            exclusive_schema=True,
        )
        try:
            await finish(upgrade_schema(engine=engine, target_version=target_version))
        finally:
            await finish(engine.dispose())


@final
class SQLiteUnitOfWorkFactory(UnitOfWorkFactory["SQLiteTransaction"]):
    """Acquire an unpooled operation resource with bounded per-factory concurrency."""

    def __init__(self, *, settings: SQLiteSettings, clock: Clock | None = None) -> None:
        """Capture settings without opening a database or starting background work."""
        self._settings = settings
        self._clock = clock if clock is not None else _utc_now
        self._slots = asyncio.Semaphore(settings.concurrency)
        self._initialization = asyncio.Lock()
        self._initialized = False

    async def _initialize_default(self) -> None:
        if self._settings.initialize_on_first_use and not self._initialized:
            async with self._initialization:
                if not self._initialized:
                    await SchemaManager(settings=self._settings).initialize()
                    self._initialized = True

    @override
    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[SQLiteTransaction]:
        async with self._slots:
            await self._initialize_default()
            engine = create_engine(
                path=self._settings.path,
                timeout=self._settings.busy_timeout,
                create=False,
            )
            try:
                await finish(prepare_schema(engine=engine, initialize=False))
                async with open_operation(engine=engine, clock=self._clock) as transaction:
                    yield transaction
            finally:
                await finish(engine.dispose())


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)
