from __future__ import annotations

import pytest

from domain_kernel.discovery.application.schema_evidence import Witness, resolve_witness


@pytest.mark.parametrize(
    ("text", "quote", "expected"),
    [
        (
            "Heading\nA work order\n  references equipment.",
            "A work order references equipment.",
            "A work order\n  references equipment.",
        ),
        ("A\nB and A\tB", "A B", None),
        ("A\nA\nA", "A A", None),
        ("A\nB and A B", "A B", "A B"),
        ("A record must identify its owner.", "A record may identify its owner.", None),
        ("A\nB", "  ", None),
    ],
)
def test_source_quote_restores_only_unique_whitespace_matches(
    text: str, quote: str, expected: str | None
) -> None:
    witness = resolve_witness(item=Witness(citation=1, quote=quote), texts=(text,))
    assert (witness.quote if witness is not None else None) == expected
