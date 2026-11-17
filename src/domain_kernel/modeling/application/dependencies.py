"""Materialize released dependencies through explicit operation-local readers."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, final, runtime_checkable

from domain_kernel.bundles import require_valid_bundle
from domain_kernel.modeling.domain.dependencies import dependency_closure, dependency_definitions
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import (
    InvalidBundleError,
    MissingCapabilityError,
    ScopeMismatchError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle
    from domain_kernel.shared.contracts import ModelScope, ModelVersion, PinnedDefinitionReference


class DependencyPins(Protocol, metaclass=ABCMeta):
    """Read one workspace's declared direct pins."""

    @abstractmethod
    async def pins(self, *, scope: ModelScope) -> tuple[ModelVersion, ...]:
        """Read ordered pins without loading their payloads."""


class ExactReleaseReader(Protocol, metaclass=ABCMeta):
    """Retrieve one registered archive by its scope and exact version."""

    @abstractmethod
    async def bundle(self, *, scope: ModelScope, version: str) -> DomainModelBundle:
        """Return the requested release or signal that the release is unavailable."""


@final
class PublishedDependencies:
    """Load a complete dependency closure inside the calling operation."""

    def __init__(self, *, pins: DependencyPins, releases: ExactReleaseReader) -> None:
        """Bind the source of selected pins and the exact release reader."""
        self._pins = pins
        self._releases = releases

    async def registered(self, *, pin: ModelVersion) -> DomainModelBundle:
        """Verify one exact release pin by scope, version and digest."""
        archive = await self._releases.bundle(scope=pin.scope, version=pin.version)
        if archive.model_version != pin:
            raise InvalidBundleError(
                issues=(
                    Issue(
                        code="dependency_pin",
                        path=("dependencies", pin.scope.model_id.value),
                        message="Select the exact version and digest of the dependency.",
                    ),
                ),
            )
        require_valid_bundle(bundle=archive)
        return archive

    async def materialize(
        self, *, scope: ModelScope, pins: Sequence[ModelVersion]
    ) -> tuple[DomainModelBundle, ...]:
        """Verify direct releases and require a compatible transitive closure."""
        if any(pin.scope.project_id != scope.project_id for pin in pins):
            raise ScopeMismatchError
        selected = [await self.registered(pin=pin) for pin in pins]
        _ = dependency_closure(scope=scope, bundles=selected)
        return tuple(selected)

    async def definitions(
        self, *, scope: ModelScope
    ) -> dict[PinnedDefinitionReference, Definition]:
        """Read the current exact closure selected for workspace validation."""
        bundles = await self.materialize(scope=scope, pins=await self._pins.pins(scope=scope))
        return dependency_definitions(scope=scope, bundles=bundles)


@runtime_checkable
class DependencyTransaction(Protocol, metaclass=ABCMeta):
    """Optional exact-release capabilities inside an active transaction."""

    @property
    @abstractmethod
    def dependencies(self) -> PublishedDependencies:
        """Return the operation's materializer."""


async def materialize_dependencies(
    *,
    resolver: PublishedDependencies | None,
    scope: ModelScope,
    pins: Sequence[ModelVersion],
) -> tuple[DomainModelBundle, ...]:
    """Resolve declared pins, allowing ordinary workspaces on simpler hosts."""
    if not pins:
        return ()
    if resolver is None:
        raise MissingCapabilityError(message="Configure access to exact published dependencies")
    return await resolver.materialize(scope=scope, pins=pins)
