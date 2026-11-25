"""Prevent an expired discovery worker from committing after lease takeover."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, final

import pytest

from domain_kernel import (
    Client,
    ClientConfiguration,
    ClientIntegrations,
    ModelRequest,
    ModelResponse,
    RunStatus,
    StaleStateError,
)
from domain_kernel._database import SQLiteSettings, SQLiteUnitOfWorkFactory
from domain_kernel.discovery.application.workflow import DiscoveryWorkflow
from tests.support.discovery.create_discovery_workspace import (
    create_discovery_workspace,
)
from tests.support.discovery.v23_gateway import V23Gateway

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import DiscoveryResult, Model
    from domain_kernel.discovery.application.workflow import (
        _Worker,  # pyright: ignore[reportPrivateUsage] -- Capture the caller's lease and version at the gate.
    )
    from domain_kernel.discovery.domain.models import SourceCheckpoint
    from domain_kernel.reconciliation.domain.models import Alignment
    from domain_kernel.shared.errors import DomainKernelError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_expired_discovery_worker_cannot_commit_after_takeover(tmp_path: Path) -> None:
    _, revision = await create_discovery_workspace(path=tmp_path, gateway=None)
    now = datetime.now(tz=UTC)
    started, finish = asyncio.Event(), asyncio.Event()

    class SlowGateway:
        supports_schema_discovery: bool = True

        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            started.set()
            _ = await finish.wait()
            return await V23Gateway().generate(request=request)

    def clock() -> datetime:
        return now

    settings = SQLiteSettings(path=tmp_path / ".domain-kernel/state.sqlite3")
    client = Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=SlowGateway()),
        integrations=ClientIntegrations(
            transactions=SQLiteUnitOfWorkFactory(settings=settings, clock=clock)
        ),
    )
    worker_model = await (await client.get_project(name="recruitment")).get_model(name="locators")
    stale = asyncio.create_task(worker_model.discover(actor="editor", sources=(revision,)))
    try:
        _ = await asyncio.wait_for(started.wait(), timeout=5)
        (interrupted,) = (await worker_model.list_discovery_runs()).items
        now += timedelta(minutes=2)
        successor = Client(
            config=ClientConfiguration(base_dir=tmp_path, model_gateway=V23Gateway()),
            integrations=ClientIntegrations(
                transactions=SQLiteUnitOfWorkFactory(settings=settings, clock=clock)
            ),
        )
        reopened = await (await successor.get_project(name="recruitment")).get_model(
            name="locators"
        )
        recovered = await reopened.resume_discovery(actor="operator", run_id=interrupted.id)
        finish.set()
        with pytest.raises(StaleStateError):
            _ = await asyncio.wait_for(stale, timeout=5)
        assert recovered.status is RunStatus.NEEDS_REVIEW
        assert await reopened.get_discovery_run(run_id=recovered.id) == recovered
        assert len((await reopened.list_review_cases(run_id=recovered.id)).items) == 1
    finally:
        if not stale.done():
            _ = stale.cancel()
            _ = await asyncio.gather(stale, return_exceptions=True)


@final
class _DiscoveryTakeoverGates:
    """Pause each caller just before its selected checkpoint transaction."""

    def __init__(self, *, timeout: int) -> None:
        self._timeout = timeout
        self.original_waiting = asyncio.Event()
        self.resume_waiting = asyncio.Event()
        self.release_original = asyncio.Event()
        self.release_resume = asyncio.Event()
        self.checkpoints: dict[str, tuple[str, int]] = {}
        self.original: asyncio.Task[DiscoveryResult] | None = None
        self.resumed: asyncio.Task[DiscoveryResult] | None = None

    def install(self, *, monkeypatch: pytest.MonkeyPatch) -> None:
        # Only control entry timing. Both callers still execute the real transaction.
        checkpoint = DiscoveryWorkflow._checkpoint  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

        async def pause_checkpoint(  # noqa: PLR0913 - Forward the real checkpoint arguments unchanged.
            workflow: DiscoveryWorkflow,
            *,
            worker: _Worker,
            status: RunStatus,
            task: SourceCheckpoint | None = None,
            report: bool = True,
            consolidated: Alignment | None = None,
            modeling_error: DomainKernelError | None = None,
            modeling_errors: tuple[DomainKernelError, ...] = (),
        ) -> None:
            caller = asyncio.current_task()
            if caller is self.original and status is RunStatus.RECONCILING:
                self.checkpoints["original"] = (worker.lease.owner, worker.run.snapshot.version)
                self.original_waiting.set()
                _ = await asyncio.wait_for(self.release_original.wait(), timeout=self._timeout)
            elif caller is self.resumed and status is RunStatus.EXTRACTING:
                self.checkpoints["resumed"] = (worker.lease.owner, worker.run.snapshot.version)
                self.resume_waiting.set()
                _ = await asyncio.wait_for(self.release_resume.wait(), timeout=self._timeout)
            await checkpoint(
                workflow,
                worker=worker,
                status=status,
                task=task,
                report=report,
                consolidated=consolidated,
                modeling_error=modeling_error,
                modeling_errors=modeling_errors,
            )

        monkeypatch.setattr(DiscoveryWorkflow, "_checkpoint", pause_checkpoint)

    async def close(self) -> None:
        tasks = [caller for caller in (self.original, self.resumed) if caller is not None]
        for caller in tasks:
            if not caller.done():
                _ = caller.cancel()
        _ = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=self._timeout
        )


async def test_discovery_takeover_fences_original_checkpoint_at_same_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, revision = await create_discovery_workspace(path=tmp_path, gateway=None)
    now = datetime.now(tz=UTC)
    timeout = 10
    gates = _DiscoveryTakeoverGates(timeout=timeout)

    async def open_model() -> Model:
        client = Client(
            config=ClientConfiguration(base_dir=tmp_path, model_gateway=V23Gateway()),
            integrations=ClientIntegrations(
                transactions=SQLiteUnitOfWorkFactory(settings=settings, clock=lambda: now)
            ),
        )
        project = await client.get_project(name="recruitment")
        return await project.get_model(name="locators")

    settings = SQLiteSettings(path=tmp_path / ".domain-kernel/state.sqlite3")
    initial_model = await open_model()
    successor_model = await open_model()
    gates.install(monkeypatch=monkeypatch)
    original = asyncio.create_task(initial_model.discover(actor="editor", sources=(revision,)))
    gates.original = original
    try:
        _ = await asyncio.wait_for(gates.original_waiting.wait(), timeout=timeout)
        (interrupted,) = (await initial_model.list_discovery_runs()).items
        assert interrupted.status is RunStatus.EXTRACTING
        now += timedelta(minutes=2)
        resumed = asyncio.create_task(
            successor_model.resume_discovery(actor="operator", run_id=interrupted.id)
        )
        gates.resumed = resumed
        _ = await asyncio.wait_for(gates.resume_waiting.wait(), timeout=timeout)
        original_owner, original_version = gates.checkpoints["original"]
        resumed_owner, resumed_version = gates.checkpoints["resumed"]
        assert original_owner != resumed_owner
        persisted = await successor_model.get_discovery_run(run_id=interrupted.id)
        assert persisted == interrupted
        assert original_version == resumed_version == persisted.version

        gates.release_original.set()
        rejected = False
        try:
            _ = await asyncio.wait_for(original, timeout=timeout)
        except StaleStateError:
            rejected = True
        assert await successor_model.get_discovery_run(run_id=interrupted.id) == persisted
        assert rejected

        gates.release_resume.set()
        recovered = await asyncio.wait_for(resumed, timeout=timeout)
        assert recovered.id == interrupted.id
        assert recovered.status is RunStatus.NEEDS_REVIEW
        assert await successor_model.get_discovery_run(run_id=recovered.id) == recovered
        assert len((await successor_model.list_review_cases(run_id=recovered.id)).items) == 1
    finally:
        await gates.close()
