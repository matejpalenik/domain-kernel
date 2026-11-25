from __future__ import annotations

import ast
import os
import subprocess
import sys
from importlib.util import resolve_name

from tests.support.repository_root import REPOSITORY_ROOT


def test_domain_sources_import_no_api_application_or_infrastructure() -> None:
    package = REPOSITORY_ROOT / "src/domain_kernel"
    forbidden = {"api", "application", "infrastructure"}
    violations: list[str] = []
    domain_modules = sorted(package.glob("*/domain/**/*.py"))
    assert domain_modules, f"No domain modules found under {package}"
    for path in domain_modules:
        relative = path.relative_to(package)
        parent = ".".join(("domain_kernel", *relative.parent.parts))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imports = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = resolve_name("." * node.level + (node.module or ""), parent)
                imports = (module, *(f"{module}.{alias.name}" for alias in node.names))
            else:
                continue
            for name in imports:
                layers = name.split(".")
                if layers[0] == "domain_kernel" and (
                    len(layers) == 1 or forbidden.intersection(layers[1:])
                ):
                    violations.append(f"{relative}:{node.lineno} imports {name}")
    assert not violations, "\n".join(violations)


def test_domain_contract_imports_do_not_load_adapters() -> None:
    script = """
import importlib
import sys

modules = (
    "domain_kernel",
    "domain_kernel.shared.application.persistence",
    "domain_kernel.modeling.domain.identifiers.definition_id",
    "domain_kernel.review.domain.identifiers.review_case_id",
    "domain_kernel.sources.domain.identifiers.source_revision_id",
    "domain_kernel.shared.contracts",
    "domain_kernel.shared.errors",
)
for module in modules:
    importlib.import_module(module)

adapters = {
    "aiosqlite", "duckdb", "docling", "linkml_runtime", "openpyxl", "pydantic", "pyshacl", "rdflib",
    "boto3", "botocore", "httpx", "sqlalchemy", "sqlite3", "yaml",
}
loaded = adapters.intersection(sys.modules)
if loaded:
    raise SystemExit(f"adapter modules imported: {sorted(loaded)}")
"""
    # Coverage itself opens SQLite. Keep the import probe uninstrumented.
    environment = os.environ.copy()
    _ = environment.pop("COVERAGE_PROCESS_CONFIG", None)
    _ = environment.pop("COVERAGE_PROCESS_START", None)
    result = subprocess.run(  # noqa: S603 -- isolated interpreter runs this fixed, trusted script.
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert result.returncode == 0, result.stderr
