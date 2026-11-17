"""Verify exact host captures without using a file reader or parser."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, final

import pytest

from domain_kernel import (
    CellRange,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    CopyTo,
    EvidenceUnavailableError,
    ExternalLocation,
    Iri,
    OntologyStatement,
    ParsedGraph,
    ParsedPayload,
    ParsedSource,
    ParsedSourceOrigin,
    ParsedSourceProvider,
    ParsedTable,
    ParsedText,
    SourceInput,
    SourceRevisionMismatchError,
    SourceUnavailableError,
)
from domain_kernel.configuration import Retention

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from domain_kernel import ProcessingLimits

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@final
class _Resolver:
    def __init__(self, *, payload: ParsedPayload) -> None:
        self.payload = payload
        self.requests: list[ParsedSourceOrigin] = []
        self.available = True

    @asynccontextmanager
    async def open(
        self,
        *,
        origin: ParsedSourceOrigin,
        limits: ProcessingLimits,
    ) -> AsyncGenerator[ParsedPayload]:
        assert limits.max_source_bytes > 0
        self.requests.append(origin)
        if not self.available:
            raise SourceUnavailableError
        yield self.payload


async def test_registered_provider_resolves_only_the_exact_capture(tmp_path: Path) -> None:
    origin = ParsedSourceOrigin(
        provider="host",
        document_id="regulation",
        document_revision="official",
        captured_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    text = ParsedText(
        text="Capture the reviewed edition and locator.",
        locator=ExternalLocation(key="article:13"),
    )
    resolver = _Resolver(payload=ParsedPayload(origin=origin, parts=[text]))
    bindings = [ParsedSourceProvider(name=origin.provider, resolver=resolver)]
    config = ClientConfiguration(base_dir=tmp_path)
    client = Client(
        config=config, integrations=ClientIntegrations(parsed_source_providers=bindings)
    )
    bindings.clear()
    project = await client.create_project(actor="author", name="recruitment")
    captured = await project.ingest_source(
        actor="author",
        name="parsed-guidance",
        source=ParsedSource(origin=origin, parts=[text]),
    )
    assert not resolver.requests
    assert captured.revision.origin == origin
    (evidence,) = captured.evidence
    current = await project.get_evidence(evidence=evidence)
    assert current.excerpt == text.text
    assert current.origin == origin
    assert resolver.requests == [origin]

    with pytest.raises(EvidenceUnavailableError):
        _ = await project.get_evidence(
            evidence=replace(evidence, locator=ExternalLocation(key="other-part")),
        )
    resolver.payload = ParsedPayload(origin=origin, parts=[replace(text, text="Changed payload.")])
    with pytest.raises(SourceRevisionMismatchError):
        _ = await project.get_evidence(evidence=evidence)
    resolver.available = False
    with pytest.raises(SourceUnavailableError):
        _ = await project.get_evidence(evidence=evidence)

    later = replace(origin, captured_at=origin.captured_at + timedelta(days=1))
    captured_again = await project.ingest_source_revision(
        actor="author",
        source_id=captured.source_id,
        source=ParsedSource(origin=later, parts=[text]),
    )
    assert captured_again.revision == captured.revision
    assert captured_again.evidence == captured.evidence


async def test_retained_table_row_and_graph_resolve_without_the_host(tmp_path: Path) -> None:
    origin = ParsedSourceOrigin(
        provider="example",
        document_id="terms",
        document_revision="1",
        captured_at=datetime(2026, 11, 15, tzinfo=UTC),
    )
    table = ParsedTable(
        name="Sourced values",
        columns=["label", "factor"],
        rows=[["Current", 1.0], ["Other row", 2]],
        locator=ExternalLocation(key="table"),
        row_locators=[
            CellRange(sheet="Values", cells="A2:B2"),
            CellRange(sheet="Values", cells="A3:B3"),
        ],
    )
    graph = ParsedGraph(
        locator=ExternalLocation(key="graph"),
        statements=[
            OntologyStatement(
                subject=Iri(value="https://example.org/object"),
                predicate=Iri(value="https://example.org/related"),
                object=Iri(value="https://example.org/other"),
            )
        ],
    )
    descriptor = ParsedSource(origin=origin, parts=[table, graph])
    resolver = _Resolver(payload=descriptor.capture())
    provider = ParsedSourceProvider(name="example", resolver=resolver)
    with pytest.raises(ValueError, match="distinct"):
        _ = ClientIntegrations(parsed_source_providers=[provider, provider])
    config = ClientConfiguration(base_dir=tmp_path, retention=Retention(extracted_text=True))
    project = await Client(
        config=config,
        integrations=ClientIntegrations(parsed_source_providers=[provider]),
    ).create_project(actor="author", name="recruitment")
    with pytest.raises(SourceUnavailableError):
        _ = await project.ingest_source(
            actor="author",
            source=descriptor,
            name="original",
            retain_original=CopyTo(store="artifacts"),
        )
    response = await project.ingest_sources(
        actor="author",
        sources=[SourceInput(source=descriptor, name="captured-terms")],
    )
    (accepted,) = response.successes
    recorded = accepted.ingested_source
    assert recorded.revision.origin == origin
    assert recorded.retained_original is None

    reopened = await Client(config=config).get_project(name=project.name)
    row_citation = next(item for item in recorded.evidence if item.locator == table.row_locators[0])
    row = await reopened.get_evidence(evidence=row_citation)
    assert isinstance(row.part, ParsedTable)
    assert row.part.rows == (("Current", 1.0),)
    assert type(row.part.rows[0][1]) is float
    assert "Other row" not in row.excerpt
    assert row.excerpt not in repr(row)
    assertion = next(item for item in recorded.evidence if item.locator == graph.locator)
    assert (await reopened.get_evidence(evidence=assertion)).part == graph
    assert not resolver.requests
