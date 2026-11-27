"""Test exact definition lookup without configuring a workspace adapter."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

import pytest

from domain_kernel import (
    ConceptDefinition,
    Definition,
    DefinitionId,
    DefinitionNotFoundError,
    ModelId,
    ModelScope,
    ProjectId,
)
from domain_kernel.modeling.application.protocols.definition_reader import DefinitionReader
from domain_kernel.modeling.application.services.definition_queries_service import (
    DefinitionQueriesService,
)
from domain_kernel.shared.application.protocols.transaction_manager import TransactionManager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@dataclass(kw_only=True)
class _Transactions(TransactionManager):
    events: list[str]

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        self.events.append("begin")
        try:
            yield
        except DefinitionNotFoundError:
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")


@dataclass(kw_only=True)
class _Reader(DefinitionReader):
    expected: Definition
    events: list[str]

    @override
    async def get(
        self,
        *,
        scope: ModelScope,
        name: str | None,
        definition_id: DefinitionId | None,
        revision: int | None,
    ) -> Definition:
        assert self.events == ["begin"]
        self.events.append("read")
        assert scope == self.expected.scope
        assert name is None
        assert definition_id == self.expected.id
        if revision != self.expected.revision:
            raise DefinitionNotFoundError
        return self.expected


@pytest.mark.asyncio
async def test_exact_lookup_returns_after_commit_and_propagates_missing_revisions() -> None:
    scope = ModelScope(project_id=ProjectId(value="catalog"), model_id=ModelId(value="observed"))
    record = Definition(
        id=DefinitionId(value="entry"),
        scope=scope,
        revision=2,
        name="entry",
        display_name="Entry",
        meaning="A catalog entry.",
        body=ConceptDefinition(),
    )
    events: list[str] = []
    queries = DefinitionQueriesService(
        reader=_Reader(expected=record, events=events), transaction=_Transactions(events=events)
    )

    found = await queries.get_definition(
        scope=scope, name=None, definition_id=record.id, revision=2
    )
    assert found is record
    assert events == ["begin", "read", "commit"]

    events.clear()
    with pytest.raises(DefinitionNotFoundError):
        _ = await queries.get_definition(
            scope=scope, name=None, definition_id=record.id, revision=3
        )
    assert events == ["begin", "read", "rollback"]
