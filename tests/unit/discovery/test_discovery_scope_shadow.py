"""Exercise the local scope audit on verified relationship proposals."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter

from domain_kernel import LangGraphDiscoveryGateway
from domain_kernel.discovery.application import scope_shadow
from domain_kernel.discovery.application.claim_extraction import (
    Anchor,
    BatchResult,
    Claim,
    IdentifiedClaim,
)
from domain_kernel.discovery.infrastructure.checkpoints import Receipt
from domain_kernel.discovery.infrastructure.langgraph_gateway import (
    _Execution,  # pyright: ignore[reportPrivateUsage] -- Reuse completed inference at projection.
)
from tests.support.discovery.make_request import make_request

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("text", "quote", "meaning", "kind"),
    [
        (
            "By understanding the process, scientists can better prepare for emergencies.",
            "By understanding the process, scientists",
            "Scientists understand the process.",
            "means",
        ),
        (
            "By reviewing these recent logs, operators can detect faults.",
            "By reviewing these recent logs, operators can detect faults",
            "Operators can detect faults by reviewing recent equipment logs.",
            None,
        ),
        (
            "By reviewing these recent logs, operators can detect faults.",
            "By reviewing these recent logs, operators can detect faults",
            "Operators can detect faults by reviewing old invoices.",
            "means",
        ),
        (
            "During the summer, a technician repaired machines that still operate today.",
            "machines that still operate today",
            "The repaired machines still operate today.",
            None,
        ),
        (
            "During the summer, a technician repaired machines that still operate today.",
            "repaired machines that still operate today",
            "The technician repaired machines that still operate today.",
            "condition",
        ),
        ("A reviewer may sign a form.", "sign a form", "A reviewer must sign a form.", "modality"),
        ("A reviewer must sign a form.", "sign a form", "A reviewer signs a form.", "modality"),
        ("A reviewer does not sign a form.", "sign a form", "A reviewer signs a form.", "negation"),
        (
            "A reviewer must not sign a form.",
            "sign a form",
            "A reviewer must sign a form.",
            "negation",
        ),
        (
            "A reviewer signs a form unless it is withdrawn.",
            "A reviewer signs a form",
            "A reviewer signs a form.",
            "exception",
        ),
        (
            "If authorized, a reviewer signs a form.",
            "signs a form",
            "A reviewer signs a form.",
            "condition",
        ),
        (
            "After authorization, a reviewer signs a form.",
            "signs a form",
            "A reviewer signs a form.",
            "condition",
        ),
        (
            "A reviewer signs a form unless it is withdrawn.",
            "signs a form",
            "A reviewer signs a form unless it is withdrawn.",
            None,
        ),
        (
            "Despite the change, a reviewer can sign the form.",
            "sign the form",
            "A reviewer can sign the form.",
            "concession",
        ),
        ("A reviewer may sign a form.", "sign a form", "A reviewer may sign a form.", None),
        ("A reviewer signs a form.", "signs a form", "A reviewer signs a form.", None),
    ],
)
def test_scope_audit_preserves_the_verified_proposals(
    tmp_path: Path, *, text: str, quote: str, meaning: str, kind: str | None
) -> None:
    request = make_request(name="scope", text=text, scope="Procedures", arm="fixture")

    def finish(*, enabled: bool) -> tuple[str, dict[str, object]]:
        directory = tmp_path / str(enabled)
        engine = _Execution(
            config=LangGraphDiscoveryGateway(
                gateway=None, directory=directory, profile="fixture", scope_shadow=enabled
            ),
            request=request,
        )
        engine.receipts.append(
            Receipt(model_id="fixture", provider_endpoint=None, input_tokens=0, output_tokens=0)
        )
        accepted = [
            engine.identify(
                Claim(
                    kind="concept" if name != "action" else "relationship",
                    name=name,
                    title=text_name,
                    meaning=statement,
                    source=source,
                    target=target,
                    evidence=[Anchor(citation=1, quote=quote)],
                    conditions=[],
                    exceptions=[],
                )
            )
            for name, text_name, statement, source, target in (
                ("actor", "Actor", "The participant performing the action.", None, None),
                ("object", "Object", "The target of the action.", None, None),
                ("action", "Action", meaning, "actor", "object"),
            )
        ]
        response = engine.finish(batches=[BatchResult(passages=[1], accepted=accepted)])
        result = next(directory.rglob("*.json"))
        report = TypeAdapter(dict[str, object]).validate_json(result.read_bytes())
        return response.output_json, report

    baseline, baseline_audit = finish(enabled=False)
    observed, shadow_audit = finish(enabled=True)
    assert json.loads(observed) == json.loads(baseline)
    assert "scope_shadow" not in baseline_audit
    report = TypeAdapter(dict[str, object]).validate_python(shadow_audit["scope_shadow"])
    flags = TypeAdapter(list[dict[str, object]]).validate_python(report["findings"])
    assert report["relationships_checked"] == 1
    assert [flag["kind"] for flag in flags] == ([] if kind is None else [kind])
    if flags:
        assert flags[0]["quote"] == text
        assert flags[0]["citation"] == 1


@pytest.mark.parametrize(
    ("previous", "separator", "cleared"),
    [
        ("Orchard practitioners trim the vines to maintain their small size.", " ", True),
        ("Orchard inspectors trim the vines to maintain their small size.", " ", False),
        ("Orchard practitioners trim the vines to maintain their small size.", "\n\n", False),
        ("Orchard practitioners trim the vines to maintain the trellis.", " ", False),
        ("Orchard practitioners trim the hedges to maintain their small size.", " ", False),
    ],
)
def test_growth_control_uses_neighboring_evidence_for_the_same_actor_and_object(
    *, previous: str, separator: str, cleared: bool
) -> None:
    quote = "By controlling the growth of the vines"
    claim = _claim(
        source="orchard-enthusiast",
        target="vine-growth",
        meaning="Orchard enthusiasts control the vines' growth.",
        quote=quote,
    )
    text = f"{previous}{separator}{quote}, orchard enthusiasts can keep sightlines clear."
    request = make_request(name="nearby", text=text, scope="Procedures", arm="fixture")
    result = scope_shadow.inspect(rows=[claim], inputs=request.inputs)
    assert [finding.kind for finding in result.findings] == ([] if cleared else ["means"])
    if cleared:
        (corroboration,) = result.corroborations
        assert corroboration.corroborating_quote == previous


@pytest.mark.parametrize(
    ("previous", "source", "meaning", "cleared"),
    [
        (
            "Install the cable, a metal strand that serves as a signal channel.",
            "cable",
            "The cable transmits pulses.",
            True,
        ),
        (
            "Install the test cable, a metal strand that serves as a signal channel.",
            "cable",
            "The cable transmits pulses.",
            False,
        ),
        (
            "If connected, the cable serves as a signal channel.",
            "cable",
            "The cable transmits pulses.",
            False,
        ),
        (
            "The cable serves as a signal channel for the monitor.",
            "monitor",
            "The monitor reads pulses.",
            False,
        ),
    ],
)
def test_signal_channel_evidence_clears_the_transport_claim_without_clearing_the_trigger(
    *, previous: str, source: str, meaning: str, cleared: bool
) -> None:
    quote = "reads the pulses transmitted through the cable"
    text = f"{previous} When the test starts, the monitor {quote}."
    claim = _claim(source=source, target="pulse", meaning=meaning, quote=quote)
    request = make_request(name="nearby", text=text, scope="Procedures", arm="fixture")
    result = scope_shadow.inspect(rows=[claim], inputs=request.inputs)
    assert [finding.kind for finding in result.findings] == ([] if cleared else ["condition"])
    if cleared:
        (corroboration,) = result.corroborations
        assert corroboration.corroborating_quote == previous


def _claim(*, source: str, target: str, meaning: str, quote: str) -> IdentifiedClaim:
    return IdentifiedClaim(
        claim_id="candidate",
        kind="relationship",
        name="candidate",
        title="Candidate",
        meaning=meaning,
        source=source,
        target=target,
        evidence=[Anchor(citation=1, quote=quote)],
        conditions=[],
        exceptions=[],
    )
