"""Runtime gateway capability captured by client configuration."""

from abc import ABCMeta, abstractmethod
from typing import Never, Protocol, runtime_checkable


@runtime_checkable
class ModelGateway(Protocol, metaclass=ABCMeta):
    """A host-owned gateway registered before the inference service is available."""

    @abstractmethod
    async def generate(self, *, request: Never) -> object:
        """Provide the asynchronous generation capability."""
