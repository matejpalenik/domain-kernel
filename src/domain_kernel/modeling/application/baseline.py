"""Resolve and copy an exact registered baseline in the caller's transaction."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

from domain_kernel.bundles import require_valid_bundle
from domain_kernel.modeling.domain.baseline import copy_active_definitions
from domain_kernel.modeling.domain.snapshots import DomainModelBundle
from domain_kernel.shared.errors import ScopeMismatchError, StaleStateError
from domain_kernel.shared.validation import require_exact

if TYPE_CHECKING:
    from domain_kernel.modeling.application.dependencies import PublishedDependencies
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.contracts import ModelScope
    from domain_kernel.shared.domain.definitions import Definition


class BaselineDefinitions(Protocol, metaclass=ABCMeta):
    """Writable active-definition inventory for an independent model."""

    @abstractmethod
    async def reserve(self, *, definition: Definition) -> None:
        """Reserve the copied identity and local name."""

    @abstractmethod
    async def append(self, *, definition: Definition) -> None:
        """Store the first active revision of that identity."""


async def load_copy_source(
    *,
    source: DomainModelBundle,
    project_id: ProjectId,
    releases: PublishedDependencies,
) -> DomainModelBundle:
    """Verify the supplied portable copy matches the exact registered source."""
    require_exact(value=source, expected=DomainModelBundle, field="Published copy source")
    if source.scope.project_id != project_id:
        raise ScopeMismatchError
    require_valid_bundle(bundle=source)
    stored = await releases.registered(pin=source.model_version)
    if stored != source:
        raise StaleStateError(message="Use the exact registered source publication for the copy")
    return stored


async def initialize_copy(
    *,
    scope: ModelScope,
    source: DomainModelBundle,
    writer: BaselineDefinitions,
) -> None:
    """Persist copied identities as the local graph, without the source's approval history."""
    for item in copy_active_definitions(source=source, scope=scope):
        await writer.reserve(definition=item)
        await writer.append(definition=item)
