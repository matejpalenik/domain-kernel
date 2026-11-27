from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from domain_kernel.discovery.application.contracts.model_request import ModelRequest
    from domain_kernel.discovery.application.contracts.model_response import ModelResponse


@runtime_checkable
class ModelGateway(Protocol, metaclass=ABCMeta):
    """A host-owned gateway that accepts the SDK's detached request."""

    @abstractmethod
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Run the asynchronously configured provider."""
