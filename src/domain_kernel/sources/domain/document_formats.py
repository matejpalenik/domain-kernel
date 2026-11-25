"""Document input capabilities of the supported Docling release."""

from enum import StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType


class DocumentFormat(StrEnum):
    """Stable SDK names for Docling input families."""

    DOCX = "docx"
    DOC = "doc"
    RTF = "rtf"
    PPTX = "pptx"
    PPT = "ppt"
    HTML = "html"
    MHTML = "mhtml"
    IMAGE = "image"
    PDF = "pdf"
    ASCIIDOC = "asciidoc"
    MD = "md"
    CSV = "csv"
    XLSX = "xlsx"
    XLS = "xls"
    ODT = "odt"
    ODS = "ods"
    ODP = "odp"
    XML_USPTO = "xml_uspto"
    XML_JATS = "xml_jats"
    XML_XBRL = "xml_xbrl"
    XML_DOCLANG = "xml_doclang"
    DCLX = "dclx"
    METS_GBS = "mets_gbs"
    JSON_DOCLING = "json_docling"
    AUDIO = "audio"
    VIDEO = "video"
    VTT = "vtt"
    LATEX = "latex"
    EMAIL = "email"
    EPUB = "epub"
    BOXNOTE = "boxnote"
    IWORK_PAGES = "iwork_pages"
    IWORK_KEYNOTE = "iwork_keynote"
    IWORK_NUMBERS = "iwork_numbers"
    EBCDIC = "ebcdic"
    AFP = "afp"
    CALENDAR = "calendar"


DOCUMENT_EXTENSIONS = MappingProxyType(
    {
        DocumentFormat.DOCX: ("docx", "dotx", "docm", "dotm"),
        DocumentFormat.DOC: ("doc", "dot"),
        DocumentFormat.RTF: ("rtf",),
        DocumentFormat.PPTX: ("pptx", "potx", "ppsx", "pptm", "potm", "ppsm"),
        DocumentFormat.PPT: ("ppt", "pot", "pps"),
        DocumentFormat.PDF: ("pdf",),
        DocumentFormat.MD: ("md", "markdown", "txt", "text", "qmd", "rmd"),
        DocumentFormat.HTML: ("html", "htm", "xhtml"),
        DocumentFormat.MHTML: ("mhtml", "mht"),
        DocumentFormat.XML_JATS: ("nxml", "xml"),
        DocumentFormat.XML_XBRL: ("xbrl", "xml", "html", "htm", "xhtml"),
        DocumentFormat.XML_DOCLANG: ("dclg", "dclg.xml", "xml"),
        DocumentFormat.DCLX: ("dclx",),
        DocumentFormat.IMAGE: ("jpg", "jpeg", "png", "tif", "tiff", "bmp", "webp", "gif"),
        DocumentFormat.ASCIIDOC: ("adoc", "asciidoc", "asc"),
        DocumentFormat.CSV: ("csv",),
        DocumentFormat.XLSX: ("xlsx", "xlsm", "xltx", "xltm"),
        DocumentFormat.XLS: ("xls", "xlt"),
        DocumentFormat.ODT: ("odt", "ott"),
        DocumentFormat.ODS: ("ods", "ots"),
        DocumentFormat.ODP: ("odp", "otp"),
        DocumentFormat.XML_USPTO: ("xml", "txt"),
        DocumentFormat.METS_GBS: ("tar.gz",),
        DocumentFormat.JSON_DOCLING: ("json",),
        DocumentFormat.AUDIO: ("wav", "mp3", "m4a", "aac", "ogg", "flac"),
        DocumentFormat.VIDEO: ("mp4", "avi", "mov", "mkv", "webm"),
        DocumentFormat.VTT: ("vtt",),
        DocumentFormat.LATEX: ("tex", "latex"),
        DocumentFormat.EMAIL: ("eml", "msg"),
        DocumentFormat.EPUB: ("epub",),
        DocumentFormat.BOXNOTE: ("boxnote",),
        DocumentFormat.IWORK_PAGES: ("pages",),
        DocumentFormat.IWORK_KEYNOTE: ("key",),
        DocumentFormat.IWORK_NUMBERS: ("numbers",),
        DocumentFormat.EBCDIC: ("ebc", "ebcdic"),
        DocumentFormat.AFP: ("afp",),
        DocumentFormat.CALENDAR: ("ics", "ical", "icalendar", "ifb"),
    }
)


def document_extension(*, name: str) -> str:
    """Recognize compound suffixes before their generic suffix."""
    normalized = name.casefold()
    for extension in ("dclg.xml", "tar.gz"):
        if normalized.endswith(f".{extension}"):
            return extension
    return PurePosixPath(normalized).suffix.removeprefix(".")


def infer_document_format(*, extension: str) -> DocumentFormat | None:
    """Use standard HTML and plain text defaults; require explicit specialized containers."""
    if extension in {"xml", "json", "tar.gz", "ebc", "ebcdic"}:
        return None
    return next(
        (kind for kind, aliases in DOCUMENT_EXTENSIONS.items() if extension in aliases), None
    )
