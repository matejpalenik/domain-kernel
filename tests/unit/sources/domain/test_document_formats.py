"""Verify format inference for explicitly supported document suffixes."""

from domain_kernel import DocumentFormat
from domain_kernel.sources.domain.document_formats import DOCUMENT_EXTENSIONS, infer_document_format


def test_suffixes_do_not_guess_schema_specific_formats() -> None:
    assert infer_document_format(extension="md") is DocumentFormat.MD
    assert infer_document_format(extension="dclg.xml") is DocumentFormat.XML_DOCLANG
    assert infer_document_format(extension="tar.gz") is None
    assert infer_document_format(extension="xml") is None
    assert set(DOCUMENT_EXTENSIONS) == set(DocumentFormat)
