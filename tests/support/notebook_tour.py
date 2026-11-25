"""Run the live notebook's code with test inputs at its external boundaries."""

from __future__ import annotations

import argparse
import json
import re
from functools import partialmethod
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from pydantic import TypeAdapter

from domain_kernel import DocumentSpan, ModelResponse
from domain_kernel.discovery.application.prompts import DEFAULT_INSTRUCTIONS
from domain_kernel.shared.hashing import hash_bytes
from examples.notebooks._preview.validation import FOLDER, Coverage, execute
from examples.notebooks.originals import Original

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel import LiteLLMGateway, ModelRequest

_CONTENT = {
    58: "Article 11 Technical documentation supports assessment of the high-risk system.",
    59: "Article 13 Instructions for use help the deployer use the system.",
    60: "Article 13 Where relevant, describe mechanisms that collect, store and interpret logs.",
}
_PAGE_COUNT = 144


def _pdf(*, path: Path, count: int, content: dict[int, str]) -> None:
    children = " ".join(f"{number} 0 R" for number in range(4, 4 + count * 2, 2))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{children}] /Count {count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for number in range(1, count + 1):
        contents = 3 + number * 2
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {contents} 0 R >>"
            ).encode()
        )
        text = content.get(number, f"Test document page {number}")
        stream = f"BT /F1 12 Tf 30 700 Td ({text}) Tj ET".encode()
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    payload = bytearray(b"%PDF-1.7\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(payload)
    payload.extend(f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(
        f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    _ = path.write_bytes(payload)


def _load(*, directory: Path, identifiers: Sequence[str], download: bool) -> dict[str, Original]:
    """Provide PDFs for the real parser while isolating the publisher network."""
    del download
    directory.mkdir(parents=True, exist_ok=True)
    result: dict[str, Original] = {}
    for name in identifiers:
        path = directory / f"{name}.pdf"
        if not path.exists():
            if name == "ai-act-en":
                _pdf(path=path, count=_PAGE_COUNT, content=_CONTENT)
            else:
                raise AssertionError(name)
        result[name] = Original(
            relative_path=path.name,
            digest=hash_bytes(content=path.read_bytes()),
        )
    return result


async def _generate(
    _gateway: LiteLLMGateway, *, request: ModelRequest, invalid_endpoint: bool = False
) -> ModelResponse:
    """Return variable-shaped decisions for the exact parsed page inputs."""
    frame = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
    assert frame["modeling_instructions"] == DEFAULT_INSTRUCTIONS
    if invalid_endpoint and request.provider_stage == "schema-compact-draft":
        return ModelResponse(
            output_json='{"concepts":', model_id="test/luna", input_tokens=300, output_tokens=50
        )
    refs: dict[int, str] = {}
    for part in request.inputs:
        page = next(
            (item.locator.page for item in part.evidence if isinstance(item.locator, DocumentSpan)),
            None,
        )
        if page is not None and (alias := re.match(r"^\[(E\d+\.\d+)\]", part.text)):
            _ = refs.setdefault(page, alias[1])
    assert set(refs) == set(range(1, _PAGE_COUNT + 1))
    fact = {
        "question_ids": ["purpose"],
        "modality": "descriptive",
        "qualifiers": [],
        "applicability": "The pinned example.",
    }
    if request.provider_stage == "schema-compact-draft":
        body: dict[str, object] = {
            "concepts": [
                {
                    **fact,
                    "name": "instructions-for-use",
                    "display_name": "Instructions for use",
                    "meaning": "Information for deployers.",
                    "witnesses": [refs[59], refs[60]],
                }
            ],
            "relationships": [],
            "questions": [],
            "unresolved_facets": [],
        }
    else:
        assert request.provider_stage == "schema-compact-repair"
        body = {
            "upsert": {"concepts": [], "relationships": [], "questions": []},
            "drop": [],
            "label_edits": [],
            "label_flags": [],
            "checks": [
                {
                    "facet_id": 1,
                    "example": _CONTENT[59],
                    "contrast": None,
                    "status": "supported",
                    "concepts": ["instructions-for-use"],
                    "links": [],
                    "witnesses": [refs[59]],
                    "reason": "Article 13 identifies instructions for use.",
                }
            ],
        }
    return ModelResponse(
        output_json=json.dumps(body),
        model_id="test/luna",
        input_tokens=300,
        output_tokens=50,
    )


def install_inputs(*, invalid_endpoint: bool = False) -> None:
    """Install only test-owned credentials, files and provider responses."""
    _ = patch("examples.notebooks.originals.load_originals", new=_load).start()
    _ = patch("examples.notebooks.live_discovery.official_api_key", return_value="test-key").start()
    _ = patch(
        "domain_kernel.LiteLLMGateway.generate",
        new=partialmethod(_generate, invalid_endpoint=invalid_endpoint),
    ).start()


class _Options(argparse.Namespace):
    verify_resume: bool = False
    invalid_endpoint: bool = False


def main() -> None:
    """Exercise the notebook twice with deterministic test inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--verify-resume", action="store_true")
    _ = parser.add_argument("--invalid-endpoint", action="store_true")
    options = parser.parse_args(namespace=_Options())
    coverage = Coverage.model_validate_json((FOLDER / "coverage.json").read_bytes())
    draft_step = next(step for step in coverage.steps if step.anchor == "draft")
    draft_step.expected_output["c4-sdk-resume-run"].append(
        "No validated draft. The handoff below uses the sample reviewer's source evidence."
        if options.invalid_endpoint
        else "instructions-for-use · PDF pages"
    )
    execute(
        coverage=coverage,
        verify_resume=options.verify_resume,
        bootstrap=(
            f"import runpy\nrunpy.run_path({str(Path(__file__).resolve())!r})['install_inputs']"
            f"(invalid_endpoint={options.invalid_endpoint!r})\n"
        ),
    )


if __name__ == "__main__":
    # The harness is also executed directly from an unpacked tour.
    main()
