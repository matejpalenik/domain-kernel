"""Verify campaign accounting without reaching an external provider."""

from dataclasses import replace
from pathlib import Path

import pytest

from domain_kernel import LiteLLMGateway, ModelResponse
from domain_kernel.discovery.application.errors.truncated_response_error import (
    TruncatedResponseError,
)
from examples.notebooks.live_campaign import (
    CampaignBudget,
    CampaignBudgetError,
    CampaignGateway,
    Usage,
)
from tests.support.discovery.make_request import make_request


def test_reported_usage_releases_only_its_own_reservation(tmp_path: Path) -> None:
    path = tmp_path / "campaign.sqlite3"
    first = CampaignBudget(path=path, max_input=20, max_output=10)
    timed_out = first.reserve(
        request_id="extraction",
        stage="smoke",
        input_tokens=8,
        output_tokens=4,
    )
    retry = first.reserve(
        request_id="extraction",
        stage="smoke",
        input_tokens=8,
        output_tokens=4,
    )
    assert timed_out != retry
    first.settle(
        identifier=retry,
        response=ModelResponse(output_json="{}", model_id="luna", input_tokens=3, output_tokens=2),
    )
    second_stage = CampaignBudget(path=path, max_input=20, max_output=10)
    assert second_stage.usage() == Usage(attempts=2, input_tokens=11, output_tokens=6)
    assert second_stage.usage(status="completed") == Usage(
        attempts=1, input_tokens=3, output_tokens=2
    )
    reserved = second_stage.usage(status="reserved")
    assert reserved == Usage(attempts=1, input_tokens=8, output_tokens=4)
    with pytest.raises(CampaignBudgetError, match="campaign token limit"):
        _ = second_stage.reserve(
            request_id="integrated",
            stage="integrated",
            input_tokens=10,
            output_tokens=1,
        )
    _ = second_stage.reserve(
        request_id="integrated",
        stage="integrated",
        input_tokens=9,
        output_tokens=4,
    )
    assert first.usage() == Usage(attempts=3, input_tokens=20, output_tokens=10)


@pytest.mark.asyncio
async def test_uncapped_luna_request_reserves_provider_ceiling(tmp_path: Path) -> None:
    ceiling = 128_000
    budget = CampaignBudget(path=tmp_path / "campaign.sqlite3", max_output=ceiling)

    async def completion(**kwargs: object) -> object:
        assert "max_completion_tokens" not in kwargs
        assert budget.usage(status="reserved").output_tokens == ceiling
        return {
            "model": "luna",
            "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 8},
        }

    gateway = CampaignGateway(
        gateway=LiteLLMGateway(api_key="fixture", completion=completion),
        budget=budget,
        stage="coverage",
    )
    request = replace(
        make_request(name="article", text="A test article.", scope="Notes", arm="test"),
        use_provider_output_limit=True,
    )
    _ = await gateway.generate(request=request)
    assert budget.usage() == Usage(attempts=1, input_tokens=5, output_tokens=8)
    with pytest.raises(CampaignBudgetError, match="campaign token limit"):
        _ = await gateway.generate(request=request)
    assert budget.usage().attempts == 1


@pytest.mark.asyncio
async def test_truncated_provider_response_settles_its_returned_usage(tmp_path: Path) -> None:
    async def completion(**_kwargs: object) -> object:
        return {
            "model": "luna",
            "choices": [{"finish_reason": "length", "message": {"content": "{"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 8},
        }

    budget = CampaignBudget(path=tmp_path / "campaign.sqlite3")
    gateway = CampaignGateway(
        gateway=LiteLLMGateway(api_key="fixture", max_output_tokens=8, completion=completion),
        budget=budget,
        stage="extract",
    )
    request = make_request(name="article", text="A test article.", scope="Notes", arm="test")
    with pytest.raises(TruncatedResponseError):
        _ = await gateway.generate(request=request)

    assert budget.usage(status="completed") == Usage(attempts=1, input_tokens=5, output_tokens=8)
    assert budget.usage(status="reserved") == Usage(attempts=0, input_tokens=0, output_tokens=0)
