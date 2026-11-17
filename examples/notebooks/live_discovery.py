"""Run the opt-in, budgeted Luna smoke check against a pinned AI Act page."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel import (
    PDF,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    DoclingParser,
    InferenceError,
    LiteLLMGateway,
    MissingCapabilityError,
    ModelKind,
)
from domain_kernel.configuration import FilesystemReader, InferencePolicy, Retention
from examples.notebooks.live_campaign import DEFAULT_LEDGER, CampaignBudget, CampaignGateway
from examples.notebooks.originals import load_originals

if TYPE_CHECKING:
    from collections.abc import Mapping

    from domain_kernel.shared.hashing import JsonValue


_ROOT = Path(__file__).resolve().parents[2]
_RECEIPT = _ROOT / "local/discovery-luna-smoke.json"
_PAGE = 46


@runtime_checkable
class _Dotenv(Protocol):
    def dotenv_values(
        self, *, dotenv_path: Path, interpolate: bool
    ) -> Mapping[str, str | None]: ...


def _official_key() -> str:
    path = _ROOT / ".env"
    if not path.is_file():
        raise MissingCapabilityError(message="Add OPENAI_API_KEY to the repository-root .env.")
    try:
        dotenv = import_module(name="dotenv")
    except ImportError:
        raise MissingCapabilityError(message="Install the Domain Kernel inference extra.") from None
    if not isinstance(dotenv, _Dotenv):
        raise MissingCapabilityError(message="Install the Domain Kernel inference extra.")
    key = dotenv.dotenv_values(dotenv_path=path, interpolate=False).get("OPENAI_API_KEY")
    if key is None or not key.strip():
        raise MissingCapabilityError(message="Add OPENAI_API_KEY to the repository-root .env.")
    return key


async def smoke(*, originals_root: Path, budget: CampaignBudget) -> dict[str, JsonValue]:
    """Test one small actual extraction through the public SDK against the official endpoint."""
    originals = await asyncio.to_thread(load_originals, directory=originals_root)
    original = originals["ai-act-en"]
    gateway = CampaignGateway(
        gateway=LiteLLMGateway(
            api_key=await asyncio.to_thread(_official_key), max_output_tokens=512
        ),
        budget=budget,
        stage="smoke",
    )
    with TemporaryDirectory(prefix="domain-kernel-discovery-smoke-") as workspace:
        config = ClientConfiguration(
            base_dir=Path(workspace),
            readers=[FilesystemReader(name="inputs", root=originals_root)],
            retention=Retention(extracted_text=True),
            inference=InferencePolicy(max_attempts=1, timeout_seconds=45.0),
            model_gateway=gateway,
        )
        project = await Client(
            config=config,
            integrations=ClientIntegrations(format_parsers={"pdf": DoclingParser()}),
        ).create_project(actor="demo:developer", name="recruitment-smoke")
        source = await project.ingest_source(
            actor="demo:developer",
            name="ai-act",
            source=PDF(
                path=original.relative_path,
                expected_hash=original.digest,
                pages=[_PAGE],
            ),
        )
        model = await project.create_model(
            actor="demo:developer",
            name="recruitment",
            kind=ModelKind.OBSERVED,
            description="Describe verified roles in recruitment AI.",
        )
        draft = await model.extract_proposals(
            actor="demo:developer",
            source_revisions=[source.revision],
            additional_instructions=(
                "Return one concept with name ai-system and display name AI system. "
                "Use citations [1] and confidence null. Leave relationships empty."
            ),
        )
        return {
            "status": "observed",
            "source": original.digest.value,
            "page": _PAGE,
            "provider_model": draft.provenance.provider_model_id,
            "provider_endpoint": draft.provenance.provider_endpoint,
            "provider_request": draft.provenance.provider_request_id,
            "prompt_hash": draft.prompt.instructions_hash.value,
            "schema_hash": draft.prompt.response_schema_hash.value,
            "input_tokens": draft.provenance.input_tokens,
            "output_tokens": draft.provenance.output_tokens,
            "proposals": [proposal.definition.name for proposal in draft.proposals],
        }


def main() -> None:
    """Keep provider failure separate from the automated notebook replay."""
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--originals", type=Path, required=True)
    options = cli.parse_args()
    # Use LiteLLM's bundled cost metadata for the official endpoint.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    budget = CampaignBudget(path=DEFAULT_LEDGER)
    try:
        result = asyncio.run(smoke(originals_root=Path(options.originals).resolve(), budget=budget))
    except (InferenceError, MissingCapabilityError) as error:
        result = {"status": "incomplete", "code": error.code, "reason": str(error)}
    total = budget.usage()
    result["campaign"] = {
        "attempts": total.attempts,
        "input_tokens": total.input_tokens,
        "output_tokens": total.output_tokens,
    }
    report = json.dumps(result, indent=2) + "\n"
    _RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    _ = _RECEIPT.write_text(report, encoding="utf-8")
    _ = sys.stdout.write(report)


if __name__ == "__main__":
    main()
