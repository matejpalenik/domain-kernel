"""Binding for the durable discovery workflow's exact run snapshots."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.shared.application.protocols.transaction import Transaction

if TYPE_CHECKING:
    from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
    from domain_kernel.discovery.domain.models import DiscoveryResult, DiscoveryRun
    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope


class DiscoveryRuns(Protocol, metaclass=ABCMeta):
    """Read and version discovery state inside an operation transaction."""

    @abstractmethod
    async def add(self, *, run: DiscoveryRun) -> None:
        """Register the exact request before it can start work."""

    @abstractmethod
    async def get(self, *, scope: ModelScope, run_id: DiscoveryRunId) -> DiscoveryRun:
        """Read the current exact run in its owning model scope."""

    @abstractmethod
    async def save(self, *, run: DiscoveryRun, expected_version: int) -> None:
        """Compare and advance one persisted checkpoint."""

    @abstractmethod
    async def list(
        self,
        *,
        scope: ModelScope,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[DiscoveryResult]:
        """Read a bounded page of detached current run results."""


@runtime_checkable
class DiscoveryTransaction(Transaction, Protocol, metaclass=ABCMeta):
    """Bind the run repository and operation leases to one session."""

    @property
    @abstractmethod
    def discovery_runs(self) -> DiscoveryRuns:
        """Return the repository sharing this transaction."""
