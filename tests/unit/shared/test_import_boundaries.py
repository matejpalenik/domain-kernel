from __future__ import annotations

import subprocess
import sys


def test_domain_contract_imports_do_not_load_adapters() -> None:
    script = """
import importlib
import sys

modules = (
    "domain_kernel",
    "domain_kernel.modeling.domain.identifiers.definition_id",
    "domain_kernel.review.domain.identifiers.review_case_id",
    "domain_kernel.sources.domain.identifiers.source_revision_id",
    "domain_kernel.shared.contracts",
    "domain_kernel.shared.errors",
)
for module in modules:
    importlib.import_module(module)

adapters = {"duckdb", "docling", "openpyxl", "pydantic", "pyshacl", "rdflib", "sqlite3"}
loaded = adapters.intersection(sys.modules)
if loaded:
    raise SystemExit(f"adapter modules imported: {sorted(loaded)}")
"""
    result = subprocess.run(  # noqa: S603 -- isolated interpreter runs this fixed, trusted script.
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
