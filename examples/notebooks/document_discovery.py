"""Run staged discovery against the pinned publisher PDF and reopen the result locally."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from domain_kernel import (
    PDF,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    DoclingParser,
    DocumentSpan,
    LangGraphDiscoveryGateway,
    LiteLLMGateway,
    Model,
    ModelKind,
    ModelNotFoundError,
    Project,
    ProjectNotFoundError,
)
from domain_kernel.configuration import FilesystemReader, InferencePolicy, Retention
from examples.notebooks.live_campaign import CampaignBudget, CampaignGateway
from examples.notebooks.live_discovery import official_api_key
from examples.notebooks.originals import load_originals

_ROOT = Path(__file__).resolve().parents[2]


def configured_client(
    *, workspace: Path, originals: Path, offline: bool = False
) -> tuple[Client, CampaignBudget, LangGraphDiscoveryGateway]:
    """Open the demo workspace with a bounded Luna provider or a replay-only journal."""
    _ = os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    budget = CampaignBudget(path=workspace / "usage.sqlite3", max_input=950_000, max_output=95_000)
    gateway = None
    if not offline:
        luna = LiteLLMGateway(
            model="openai/gpt-6-luna",
            api_key=official_api_key(),
            reasoning_effort="none",
            max_output_tokens=6144,
        )
        gateway = CampaignGateway(gateway=luna, budget=budget, stage="document-discovery")
    graph = LangGraphDiscoveryGateway(
        gateway=gateway,
        directory=workspace / "workflow",
        profile="https://api.openai.com/v1/openai/gpt-6-luna/none/6144",
    )
    client = Client(
        config=ClientConfiguration(
            base_dir=workspace,
            readers=[FilesystemReader(name="inputs", root=originals.resolve())],
            retention=Retention(extracted_text=True),
            inference=InferencePolicy(
                max_attempts=1, timeout_seconds=1200.0, max_input_bytes=8_000_000, max_proposals=512
            ),
            model_gateway=graph,
        ),
        integrations=ClientIntegrations(format_parsers={"pdf": DoclingParser.for_discovery()}),
    )
    return client, budget, graph


async def open_recruitment_model(*, client: Client, actor: str) -> tuple[Project, Model]:
    """Open the walkthrough's project and scoped recruitment model on a restart."""
    try:
        project = await client.get_project(name="employment-policy")
    except ProjectNotFoundError:
        project = await client.create_project(name="employment-policy", actor=actor)
    try:
        model = await project.get_model(name="recruitment")
    except ModelNotFoundError:
        model = await project.create_model(
            name="recruitment",
            actor=actor,
            kind=ModelKind.OBSERVED,
            description=(
                "Describe how AI systems are used in recruitment and selection, "
                "who is involved, and their responsibilities."
            ),
        )
    return project, model


async def run(*, workspace: Path, originals: Path, ingest_only: bool, offline: bool) -> None:
    """Process the pinned complete source and print the SDK result and audit location."""
    source = await asyncio.to_thread(
        load_originals, directory=originals, identifiers=["ai-act-en"], download=not offline
    )
    act = source["ai-act-en"]
    client, budget, graph = configured_client(
        workspace=workspace, originals=originals, offline=offline
    )
    actor = "demo:discovery-reader"
    project, model = await open_recruitment_model(client=client, actor=actor)
    captured = await project.ingest_source(
        actor=actor,
        name="english-ai-act",
        source=PDF(path=act.relative_path, expected_hash=act.digest),
        idempotency_key="ingest-v1",
    )
    pages = {
        e.locator.page
        for e in captured.evidence
        if isinstance(e.locator, DocumentSpan) and e.locator.section is None
    }
    if pages != set(range(1, 145)):
        raise RuntimeError("The full edition requires 144 physical PDF pages.")
    _ = sys.stdout.write(
        f"Verified {len(pages)} pages, {len(captured.evidence)} evidence locators; "
        f"{act.digest.value}\n"
    )
    if ingest_only:
        return
    if offline:
        replay = await model.extract_proposals(source_revisions=[captured.revision], actor=actor)
        _ = sys.stdout.write(
            f"Rebuilt {len(replay.proposals)} proposals from the journal. "
            f"Report: {graph.directory / (replay.run_id.value + '.json')}\n"
        )
        return
    result = await model.discover(
        actor=actor,
        sources=[captured.revision],
        idempotency_key="discover-verified-v3",
    )
    for failure in result.failures:
        _ = sys.stdout.write(f"{failure.code}: {failure.message}\n")
    _ = sys.stdout.write(f"{result.status.value} · {budget.usage()}\n")
    if result.failures:
        raise RuntimeError("See the run diagnostics.")
    cases = [case async for case in model.iter_review_cases(run_id=result.id)]
    _ = sys.stdout.write(
        f"{len(cases)} review cases. Report: {graph.directory / (result.id.value + '.json')}\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--ingest-only", action="store_true")
    _ = parser.add_argument("--offline", action="store_true")
    _ = parser.add_argument(
        "--workspace", type=Path, default=_ROOT / "local" / "staged-recruitment-discovery"
    )
    _ = parser.add_argument(
        "--originals",
        type=Path,
        default=_ROOT / "local/notebook-tour/recruitment-default-discovery/sources",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            workspace=args.workspace,
            originals=args.originals,
            ingest_only=args.ingest_only,
            offline=args.offline,
        )
    )
