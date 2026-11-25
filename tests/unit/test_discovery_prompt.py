"""Verify discovery prompt modes independently of model-provider output."""

from inspect import Parameter, signature

import pytest

from domain_kernel import Model
from domain_kernel.discovery.application.prompts import DEFAULT_INSTRUCTIONS, capture_prompt
from domain_kernel.shared.hashing import hash_bytes


@pytest.mark.parametrize(
    ("additional", "override", "effective", "uses_default"),
    [
        (None, None, DEFAULT_INSTRUCTIONS, True),
        (
            "Focus on recruitment.",
            None,
            f"{DEFAULT_INSTRUCTIONS}\n\nAdditional instructions:\nFocus on recruitment.",
            True,
        ),
        (None, "Focus on documentation.", "Focus on documentation.", False),
        ("Ignore this addition.", "Focus on documentation.", "Focus on documentation.", False),
    ],
)
def test_instruction_modes_preserve_the_sdk_owned_schema(
    additional: str | None,
    override: str | None,
    effective: str,
    *,
    uses_default: bool,
) -> None:
    schema = '{"type":"object"}'
    captured = capture_prompt(
        additional_instructions=additional,
        prompt_override=override,
        schema_json=schema,
    )
    assert captured.effective_instructions == effective
    assert (captured.default_prompt_version is not None) == uses_default
    assert captured.instructions_hash == hash_bytes(content=effective.encode())
    assert captured.response_schema_hash == hash_bytes(content=schema.encode())
    assert captured.additional_instructions == additional
    assert captured.prompt_override == override


@pytest.mark.parametrize(("additional", "override"), [("", None), (None, " "), (" ", "Valid")])
def test_blank_supplied_instructions_fail_even_if_ignored(
    additional: str | None,
    override: str | None,
) -> None:
    with pytest.raises(ValueError, match="nonblank"):
        _ = capture_prompt(
            additional_instructions=additional,
            prompt_override=override,
            schema_json="{}",
        )


def test_discovery_contract_exposes_both_controls_and_keeps_resume_pinned() -> None:
    controls = {"additional_instructions", "prompt_override"}
    for method in (Model.discover, Model.extract_proposals):
        params = signature(method).parameters
        assert controls <= params.keys()
        assert all(params[name].kind is Parameter.KEYWORD_ONLY for name in controls)
    assert controls.isdisjoint(signature(Model.resume_discovery).parameters)
