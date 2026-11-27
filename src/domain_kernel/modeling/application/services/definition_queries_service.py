"""Keep exact definition inspection separate from Review's write path."""

from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from domain_kernel.modeling.application.protocols.definition_queries import DefinitionQueries

if TYPE_CHECKING:
    from domain_kernel.modeling.application.protocols.definition_reader import DefinitionReader
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.shared.application.protocols.transaction_manager import TransactionManager
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope


@final
class DefinitionQueriesService(DefinitionQueries):
    """Read one definition inside an operation-local transaction."""

    def __init__(self, *, reader: DefinitionReader, transaction: TransactionManager) -> None:
        """Bind the reader and transaction manager for the same session."""
        self._reader = reader
        self._transaction = transaction

    @override
    async def get_definition(
        self,
        *,
        scope: ModelScope,
        name: str | None,
        definition_id: DefinitionId | None,
        revision: int | None,
    ) -> Definition:
        async with self._transaction.begin():
            return await self._reader.get(
                scope=scope,
                name=name,
                definition_id=definition_id,
                revision=revision,
            )
