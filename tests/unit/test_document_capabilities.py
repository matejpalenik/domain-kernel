"""Check optional adapter dependency recovery without installing providers."""

from importlib.metadata import PackageNotFoundError

import pytest

from domain_kernel import DoclingParser, DocumentFormat, MissingCapabilityError
from domain_kernel.sources.domain.document_formats import DOCUMENT_EXTENSIONS, infer_document_format
from domain_kernel.sources.infrastructure import docling_documents


def test_missing_document_engine_has_a_typed_installation_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(*, distribution_name: str) -> str:
        raise PackageNotFoundError(distribution_name)

    monkeypatch.setattr(docling_documents, "version", missing)
    with pytest.raises(MissingCapabilityError, match="documents extra"):
        _ = DoclingParser().parser_version


def test_suffixes_do_not_guess_schema_specific_formats() -> None:
    assert infer_document_format(extension="md") is DocumentFormat.MD
    assert infer_document_format(extension="dclg.xml") is DocumentFormat.XML_DOCLANG
    assert infer_document_format(extension="tar.gz") is None
    assert infer_document_format(extension="xml") is None
    assert set(DOCUMENT_EXTENSIONS) == set(DocumentFormat)
