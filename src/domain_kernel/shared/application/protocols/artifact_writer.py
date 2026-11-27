from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.shared.domain.entities.artifact import Artifact


class ArtifactWriter(Protocol, metaclass=ABCMeta):
    """Write a new artifact or recover an interrupted request."""

    @abstractmethod
    async def __call__(self, *, retry: bool) -> Artifact:
        """Return the receipt for the exact delivery request.

        Args:
            retry: Whether a prior attempt recorded an intent and may have written the bytes.
        """
