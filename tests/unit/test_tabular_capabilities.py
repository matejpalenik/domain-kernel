"""Check optional adapter dependency recovery without installing providers."""

from importlib.metadata import PackageNotFoundError

import pytest

from domain_kernel import DuckDBCSVParser, FormatParser, MissingCapabilityError, OpenpyxlExcelParser
from domain_kernel.sources.infrastructure import tabular


@pytest.mark.parametrize("parser", [DuckDBCSVParser(), OpenpyxlExcelParser()])
def test_missing_table_engine_has_a_typed_installation_hint(
    monkeypatch: pytest.MonkeyPatch,
    parser: FormatParser,
) -> None:
    def missing(*, distribution_name: str) -> str:
        raise PackageNotFoundError(distribution_name)

    monkeypatch.setattr(tabular, "version", missing)
    with pytest.raises(MissingCapabilityError, match="tabular extra"):
        _ = parser.parser_version
