"""Verify stage isolation against the actual repair and semantic recheck path."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, final, override

import pytest

from domain_kernel import (
    DiscoveryStage,
    DiscoveryStageRoute,
    InferenceError,
    LangGraphDiscoveryGateway,
    ModelGateway,
    ModelRequest,
    ModelResponse,
)
from domain_kernel.discovery.application.claim_extraction import (
    Anchor,
    BatchResult,
    Claim,
    Finding,
    IdentifiedClaim,
)
from domain_kernel.discovery.infrastructure.langgraph_gateway import (
    _Execution,  # pyright: ignore[reportPrivateUsage] -- run the real repair and recheck nodes
)
from tests.support.discovery.make_request import make_request

if TYPE_CHECKING:
    from pathlib import Path


@final
class _Gateway(ModelGateway):
    def __init__(self, *, model: str) -> None:
        self.model = model
        self.repair: IdentifiedClaim | None = None
        self.calls: list[str] = []

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        packet = request.context_json or ""
        if "disputed_claims" in packet:
            assert self.repair is not None
            self.calls.append("repair")
            output = '{"claims":[' + self.repair.model_dump_json() + "]}"
        else:
            self.calls.append("verify")
            output = '{"verdicts":[{"index":0,"status":"supported","reason":"Cited."}]}'
        return ModelResponse(model_id=self.model, output_json=output, output_tokens=1)


@pytest.mark.asyncio
async def test_routed_repair_is_rechecked_by_default_gateway_and_replays_by_profile(
    tmp_path: Path,
) -> None:
    req = make_request(name="doc", text="A reviewer may sign.", scope="Review", arm="routing")
    default = _Gateway(model="sol")
    repairer = _Gateway(model="luna")
    stage = DiscoveryStage.REPAIR
    routes = {stage: DiscoveryStageRoute(gateway=repairer, profile="luna-xhigh")}
    config = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=default,
        directory=tmp_path,
        profile="sol-low",
        stage_routes=routes,
    )
    routes.clear()
    engine = _Execution(config=config, request=req)
    claim = engine.identify(
        Claim(
            kind="concept",
            name="reviewer",
            title="Reviewer",
            meaning="A reviewer must sign.",
            evidence=[Anchor(citation=1, quote=req.inputs[0].text)],
            source=None,
            target=None,
            conditions=[],
            exceptions=[],
        )
    )
    repaired = claim.model_copy(update={"meaning": req.inputs[0].text})
    default.repair = repairer.repair = repaired
    batch = BatchResult(
        passages=[1],
        candidates=[claim],
        findings=[Finding(stage="semantic", batch=0, claim_id=claim.claim_id, detail="Use may.")],
    )
    repaired_state = await engine.checkpointed("repair", engine.repair)({"batches": [batch]})
    (result,) = repaired_state["batches"]
    assert repairer.calls == ["repair"]
    assert default.calls == ["verify"]
    assert result.accepted == [repaired]

    offline = replace(
        config,
        gateway=None,
        stage_routes={stage: DiscoveryStageRoute(gateway=None, profile="luna-xhigh")},
    )
    replay = _Execution(config=offline, request=req)
    snapshot = await replay.restore()
    assert snapshot is not None
    assert snapshot.batches == [result]
    replay = _Execution(config=offline, request=req)
    assert await replay.repair_batch(batch, 0) == result
    assert [(item.stage, item.model_id, item.profile) for item in replay.receipts] == [
        ("repair", "luna", "luna-xhigh"),
        ("verify", "sol", "sol-low"),
    ]

    alternate = replace(
        offline,
        stage_routes={stage: DiscoveryStageRoute(gateway=None, profile="different-model")},
    )
    separate = _Execution(config=alternate, request=req)
    assert await separate.restore() is None
    with pytest.raises(InferenceError, match="No exact response"):
        _ = await separate.repair_batch(batch, 0)
