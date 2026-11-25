"""The website reference describes delivered symbols and their actual source."""

import re
import subprocess
import sys

import pytest

import domain_kernel
from development.docs import reference
from tests.support.repository_root import REPOSITORY_ROOT


def test_reference_covers_only_implemented_public_exports() -> None:
    result = reference(root=REPOSITORY_ROOT)
    assert {item.name for item in result.symbols} == set(domain_kernel.__all__)
    assert "DomainKernelClient" not in {item.name for item in result.symbols}


def test_reference_preserves_inherited_fields_and_explicit_signatures() -> None:
    symbols = {item.name: item for item in reference(root=REPOSITORY_ROOT).symbols}
    identifier = symbols.get("ProjectId")
    assert identifier is not None
    assert [(field.name, field.annotation) for field in identifier.fields] == [("value", "str")]
    issue = symbols["Issue"]
    assert "*, code: str" in issue.signature
    assert "path: Sequence[str | int]" in issue.signature
    assert issue.description == "Sanitized diagnostic attached to validation and typed failures."
    assert symbols["Page"].signature.startswith("Page[T](*, items: Sequence[T]")
    assert symbols["reason_ontology"].signature.startswith(
        "async def reason_ontology(*, ontology: OntologyClosure"
    )


def test_reference_retains_enum_values_and_locatable_source() -> None:
    symbols = {item.name: item for item in reference(root=REPOSITORY_ROOT).symbols}
    status = symbols.get("CaseStatus")
    assert status is not None
    assert {member.name for member in status.members} == {
        member.name for member in domain_kernel.CaseStatus
    }
    for item in symbols.values():
        assert (REPOSITORY_ROOT / item.source).is_file()
        assert item.line > 0
        assert item.description


@pytest.mark.parametrize("page", ["quickstart", "reference"])
def test_published_python_examples_execute(page: str) -> None:
    text = (REPOSITORY_ROOT / "apps/docs/src/app" / page / "page.mdx").read_text()
    examples = [
        match.group(1) for match in re.finditer(r"```python\n(.*?)\n```", text, flags=re.DOTALL)
    ]
    assert examples
    for example in examples:
        # These are trusted, repository-owned examples executed in the test interpreter.
        result = subprocess.run(  # noqa: S603 -- fixed interpreter, reviewed source snippets
            [sys.executable, "-c", example],
            cwd=REPOSITORY_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        assert result.stdout.strip()
