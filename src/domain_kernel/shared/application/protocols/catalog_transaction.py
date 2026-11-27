from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

from domain_kernel.shared.application.protocols.transaction import Transaction

if TYPE_CHECKING:
    from domain_kernel.modeling.application.protocols.model_catalog import ModelCatalog
    from domain_kernel.projects.application.protocols.project_catalog import ProjectCatalog


class CatalogTransaction(Transaction, Protocol, metaclass=ABCMeta):
    """Operation-local resources used by project and model composition."""

    @property
    @abstractmethod
    def projects(self) -> ProjectCatalog:
        """The project repository bound to this transaction."""

    @property
    @abstractmethod
    def models(self) -> ModelCatalog:
        """The model repository bound to this transaction."""
