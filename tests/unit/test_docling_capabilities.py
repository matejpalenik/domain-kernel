"""Verify optional document adapter recovery without loading Docling."""

from importlib.metadata import PackageNotFoundError

import pytest

from domain_kernel import DoclingParser, MissingCapabilityError
from domain_kernel.sources.infrastructure import docling_documents


def test_missing_docling_extra_has_a_typed_installation_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(*, distribution_name: str) -> str:
        raise PackageNotFoundError(distribution_name)

    monkeypatch.setattr(docling_documents, "version", missing)
    with pytest.raises(MissingCapabilityError, match="documents extra"):
        _ = DoclingParser().parser_version


def test_ocr_requires_explicit_asset_directory() -> None:
    with pytest.raises(MissingCapabilityError, match="local artifacts directory"):
        _ = DoclingParser(ocr=True)
