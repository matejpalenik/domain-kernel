"""Verify campaign accounting without reaching an external provider."""

from pathlib import Path

import pytest

from domain_kernel import ModelResponse
from examples.notebooks.live_campaign import CampaignBudget, CampaignBudgetError, Usage


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
