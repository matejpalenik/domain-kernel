"""Run the opt-in recruitment discovery and update journey through budgeted Luna."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, final, override

from pydantic import BaseModel

from domain_kernel import (
    PDF,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    ConceptDefinition,
    DoclingParser,
    DocumentSpan,
    DomainModelBundle,
    EditDefinition,
    Exclude,
    LiteLLMGateway,
    ModelGateway,
    ModelKind,
    ModelResponse,
    RunStatus,
)
from domain_kernel.configuration import FilesystemReader, InferencePolicy, Retention
from domain_kernel.shared.errors import DomainKernelError
from examples.notebooks.live_campaign import DEFAULT_LEDGER, CampaignBudget, CampaignGateway
from examples.notebooks.live_discovery import official_api_key
from examples.notebooks.originals import load_originals

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel import DiscoveryResult, Model, ModelRequest, ReviewCase
    from domain_kernel.shared.hashing import JsonValue

_FOLDER = Path(__file__).resolve().parent
_RECEIPT_FOLDER = _FOLDER.parents[1] / "local" / "v23-live-discovery-integrated"
_RELEASE_RECEIPT_FOLDER = _FOLDER.parents[1] / "local" / "v23-live-discovery-release-candidate"
_EXPECTED_RELEASES = 2
_REVIEWED_MEANINGS = {
    "instructions-for-use": (
        "Information supplied to deployers for the intended and proper use of a system."
    ),
    "ai-system-definition-elements": (
        "The elements of the AI-system definition discussed by the Commission "
        "across the system lifecycle."
    ),
}
_DOCUMENTATION_PAGES = frozenset({47, 59, 60})
_GUIDANCE_PAGES = frozenset({3})
_ACT_FOCUS = (
    "Focus on recruitment systems, recruitment actors and safeguards. "
    "Preserve qualifications and supporting definitions wherever they appear. "
    "Include instructions-for-use if supported by the Act."
)
_UPDATE_FOCUS = (
    "Record how the Commission groups the elements of the AI-system definition. "
    "Use the name ai-system-definition-elements for that meaning."
)


class _ExpectedMeaning(BaseModel):
    meaning: str
    pages: tuple[int, ...]


class _CorpusExpectations(BaseModel):
    expected: tuple[_ExpectedMeaning, ...]


def _grade_act(*, cases: Sequence[ReviewCase]) -> dict[str, JsonValue]:
    """Score exact lookup names and page coverage from the frozen publisher rubric."""
    rubric = _CorpusExpectations.model_validate_json(
        (_FOLDER / "fixtures" / "discovery-expectations.json").read_bytes(),
    )
    candidates = {item.definitions[0].name: item for item in cases}
    seen: set[str] = set()
    grades: list[JsonValue] = []
    for expected in rubric.expected:
        name = re.sub(r"[^a-z0-9]+", "-", expected.meaning.casefold()).strip("-")
        actual = candidates.get(name)
        pages = () if actual is None else _pages(case=actual)
        if actual is not None:
            seen.add(name)
        grades.append(
            {
                "meaning": expected.meaning,
                "expected_pages": expected.pages,
                "reported_pages": pages,
                "matched_name": actual is not None,
                "matched_pages": tuple(sorted(set(pages).intersection(expected.pages))),
            }
        )
    return {
        "review": "Lexical and citation evidence for independent review.",
        "expected": grades,
        "extra_candidate_names": tuple(sorted(candidates.keys() - seen)),
    }


@final
@dataclass(kw_only=True)
class ObservedGateway(ModelGateway):
    """Retain provider receipts locally while the SDK validates the actual outputs."""

    upstream: CampaignGateway = field(repr=False)
    supports_schema_discovery: bool = True
    responses: list[ModelResponse] = field(default_factory=list[ModelResponse], repr=False)

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Record the exact result retained by the budgeted host."""
        response = await self.upstream.generate(request=request)
        self.responses.append(response)
        return response


def _pages(*, case: ReviewCase) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                citation.locator.page
                for citation in case.evidence
                if isinstance(citation.locator, DocumentSpan) and citation.locator.page is not None
            }
        )
    )


def _observed(
    *, run: DiscoveryResult, cases: Sequence[ReviewCase], source: str
) -> dict[str, JsonValue]:
    proposals: list[JsonValue] = [
        {
            "name": item.definitions[0].name,
            "meaning": item.definitions[0].meaning,
            "kind": item.definitions[0].kind.value,
            "pages": _pages(case=item),
            "citations": [
                {
                    "source": citation.source.revision_id.value,
                    "page": citation.locator.page,
                    "start": citation.locator.start,
                    "end": citation.locator.end,
                }
                for citation in item.evidence
                if isinstance(citation.locator, DocumentSpan)
            ],
            "uncertainty": "Review exact passage coverage during acceptance.",
        }
        for item in cases
    ]
    failures: list[JsonValue] = [
        {
            "code": failure.code,
            "message": failure.message,
            "retryable": failure.retryable,
        }
        for failure in run.failures
    ]
    return {
        "status": run.status.value,
        "source": source,
        "instructions_hash": run.prompt.instructions_hash.value,
        "schema_hash": run.prompt.response_schema_hash.value,
        "proposals": proposals,
        "failures": failures,
    }


def _complete_review(
    *,
    run: DiscoveryResult,
    cases: Sequence[ReviewCase],
    name: str,
    pages: frozenset[int],
) -> ReviewCase | None:
    if run.status is not RunStatus.NEEDS_REVIEW or run.failures:
        return None
    matches = tuple(
        item
        for item in cases
        if item.definitions[0].name == name
        and isinstance(item.definitions[0].body, ConceptDefinition)
        and pages.intersection(_pages(case=item))
    )
    return matches[0] if len(matches) == 1 else None


async def _publish(
    *,
    model: Model,
    cases: Sequence[ReviewCase],
    selected: ReviewCase,
    version: str,
) -> DomainModelBundle:
    for case in cases:
        proposed = case.definitions[0]
        decision = (
            EditDefinition(
                definition_id=proposed.id,
                name=proposed.name,
                display_name=proposed.display_name,
                meaning=_REVIEWED_MEANINGS[proposed.name],
                body=ConceptDefinition(),
                reason="Use the authored meaning after checking the exact publisher citation.",
            )
            if case.id == selected.id
            else Exclude(
                scope_text="One authored meaning per source for this demonstration",
                reason="Leave this candidate in the recorded results for the final corpus review.",
            )
        )
        _ = await model.preview_changes(case=case, decision=decision)
        _ = await model.decide_review(case=case, decision=decision, actor="demo:fixture-reviewer")
    prepared = await model.prepare_publication(actor="demo:operator")
    return await model.publish(
        publication=prepared,
        version=version,
        actor="demo:publisher",
        reason="Preserve this isolated demonstration's expressly scoped review.",
    )


def _model_receipts(*, gateway: ObservedGateway) -> tuple[JsonValue, ...]:
    return tuple(
        {
            "model": item.model_id,
            "endpoint": item.provider_endpoint,
            "input_tokens": item.input_tokens,
            "output_tokens": item.output_tokens,
            "structured_response": item.output_json,
        }
        for item in gateway.responses
    )


async def integrated(
    *,
    originals_root: Path,
    budget: CampaignBudget,
    receipt_folder: Path,
    stage: str = "integrated",
) -> dict[str, JsonValue]:
    """Exercise two separately pinned sources and reopen their reviewed releases."""
    originals = await asyncio.to_thread(load_originals, directory=originals_root)
    gateway = ObservedGateway(
        upstream=CampaignGateway(
            gateway=LiteLLMGateway(
                api_key=await asyncio.to_thread(official_api_key),
                max_output_tokens=4096,
            ),
            budget=budget,
            stage=stage,
        )
    )
    observations: list[JsonValue] = []
    releases: list[DomainModelBundle] = []
    with TemporaryDirectory(prefix="domain-kernel-discovery-integrated-") as workspace:
        config = ClientConfiguration(
            base_dir=Path(workspace),
            readers=[FilesystemReader(name="inputs", root=originals_root)],
            retention=Retention(extracted_text=True),
            inference=InferencePolicy(timeout_seconds=1200.0),
            model_gateway=gateway,
        )
        client = Client(
            config=config,
            integrations=ClientIntegrations(format_parsers={"pdf": DoclingParser()}),
        )
        project = await client.create_project(actor="demo:operator", name="recruitment-live")
        model = await project.create_model(
            actor="demo:operator",
            name="recruitment",
            kind=ModelKind.OBSERVED,
            description="Inspect the Act and separately attributed AI-system guidance.",
        )
        for source_id, instructions, concept, pages, version in (
            ("ai-act-en", _ACT_FOCUS, "instructions-for-use", _DOCUMENTATION_PAGES, "1.0.0"),
            ("guidance", _UPDATE_FOCUS, "ai-system-definition-elements", _GUIDANCE_PAGES, "1.1.0"),
        ):
            original = originals[source_id]
            source = await project.ingest_source(
                actor="demo:operator",
                name=source_id,
                source=PDF(path=original.relative_path, expected_hash=original.digest),
            )
            run = await model.discover(
                actor="demo:operator",
                sources=[source.revision],
                additional_instructions=instructions,
            )
            cases = tuple([case async for case in model.iter_review_cases(run_id=run.id)])
            observed = _observed(run=run, cases=cases, source=original.digest.value)
            if run.reconciliation_id is not None:
                alignment = await model.get_alignment(alignment_id=run.reconciliation_id)
                observed["mapping_suggestions"] = [
                    {
                        "layer": item.layer.value,
                        "definition_id": item.definition_id.value,
                        "reference_id": None
                        if item.reference_id is None
                        else item.reference_id.value,
                        "relation": None if item.relation is None else item.relation.value,
                        "reason": item.reason,
                    }
                    for item in alignment.suggestions
                ]
            selected = _complete_review(run=run, cases=cases, name=concept, pages=pages)
            if source_id == "ai-act-en":
                observed["rubric_evidence"] = _grade_act(cases=cases)
            observed["review_scope"] = {
                "requested_meaning": concept,
                "suggested_for_demo_review": selected is not None,
                "demo_review_actions": len(cases) if selected is not None else 0,
                "correction_effort": "Review omissions and extra meanings at acceptance.",
            }
            observations.append(observed)
            if selected is None:
                break
            releases.append(
                await _publish(model=model, cases=cases, selected=selected, version=version)
            )
        detached = await Client(
            config=ClientConfiguration(base_dir=Path(workspace)),
        ).get_project(name=project.name)
        consumer = await detached.get_model(name=model.info.name)
        verified: list[str] = []
        for release in releases:
            archived = await consumer.get_version(version=release.version)
            data = archived.serialize()
            if DomainModelBundle.deserialize(payload=data) != release:
                raise ValueError("The independent consumer must reopen every exact release.")
            _ = (receipt_folder / f"recruitment-{release.version}.json").write_bytes(data)
            verified.append(release.content_hash.value)
    return {
        "status": "observed" if len(releases) == _EXPECTED_RELEASES else "incomplete",
        "observations": observations,
        "provider_receipts": _model_receipts(gateway=gateway),
        "independently_reloaded_hashes": verified,
    }


def main() -> None:
    """Keep the provider evidence local and report the bounded campaign usage."""
    cli = argparse.ArgumentParser(description=__doc__)
    _ = cli.add_argument("--originals", type=Path, required=True)
    _ = cli.add_argument("--release-candidate", action="store_true")
    options = _Options()
    _ = cli.parse_args(namespace=options)
    _ = os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    receipt_folder = _RELEASE_RECEIPT_FOLDER if options.release_candidate else _RECEIPT_FOLDER
    stage = "release-candidate" if options.release_candidate else "integrated"
    receipt_folder.mkdir(parents=True, exist_ok=True)
    budget = CampaignBudget(path=DEFAULT_LEDGER)
    result: dict[str, JsonValue]
    try:
        result = asyncio.run(
            integrated(
                originals_root=options.originals.resolve(),
                budget=budget,
                receipt_folder=receipt_folder,
                stage=stage,
            )
        )
    except DomainKernelError as error:
        result = {"status": "incomplete", "code": error.code, "reason": str(error)}
    usage = budget.usage()
    result["campaign"] = {
        "attempts": usage.attempts,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }
    _ = (receipt_folder / "receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    status = f"Luna {stage} evidence: {result['status']}"
    tokens = f"{usage.input_tokens} input, {usage.output_tokens} output"
    _ = sys.stdout.write(f"{status}\nCampaign accounted tokens: {tokens}\n")


class _Options(argparse.Namespace):
    originals: Path = Path()
    release_candidate: bool = False


if __name__ == "__main__":
    main()
