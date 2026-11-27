"""Build independent persistence resources for a test backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel._database import (
    PostgreSQLSettings,
    PostgreSQLUnitOfWorkFactory,
    SQLiteSettings,
    SQLiteUnitOfWorkFactory,
)

if TYPE_CHECKING:
    from domain_kernel import ClientConfiguration
    from domain_kernel.shared.application.idempotency.clock import Clock
    from domain_kernel.shared.application.protocols.unit_of_work_factory import UnitOfWorkFactory
    from domain_kernel.shared.infrastructure.persistence.sqlalchemy_transaction import (
        SqlAlchemyTransaction,
    )


@dataclass(frozen=True, kw_only=True)
class DatabaseBackend:
    """Workspace configuration and independent low-level resources on one backend."""

    config: ClientConfiguration
    settings: SQLiteSettings | PostgreSQLSettings

    def factory(self, *, clock: Clock | None = None) -> UnitOfWorkFactory[SqlAlchemyTransaction]:
        """Create another resource factory for the same exact namespace."""
        if isinstance(self.settings, PostgreSQLSettings):
            return PostgreSQLUnitOfWorkFactory(settings=self.settings, clock=clock)
        return SQLiteUnitOfWorkFactory(settings=self.settings, clock=clock)
