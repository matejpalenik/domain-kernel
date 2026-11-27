"""Bounded, optional rendering of inspected SDK values."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from html import escape
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.bundles import BundleValidation, DomainModelBundle
from domain_kernel.diagnostics import ConfigurationReport
from domain_kernel.discovery.domain.models import DiscoveryResult
from domain_kernel.modeling.domain.interchange import ProjectionAssessment
from domain_kernel.modeling.domain.publications import Publication
from domain_kernel.modeling.domain.snapshots import Candidate, Readiness, ValidationReport
from domain_kernel.reference_packs.domain.packs import ReferencePack
from domain_kernel.review.domain.models import ReviewCase, ReviewImpact
from domain_kernel.shared.application.results.page import Page
from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.entities.concept import Concept
from domain_kernel.shared.domain.entities.definition import Definition
from domain_kernel.shared.domain.value_objects.change_set import ChangeSet
from domain_kernel.shared.errors.missing_capability_error import MissingCapabilityError
from domain_kernel.sources.application.contracts import BatchIngestionResult, IngestionSuccess
from domain_kernel.sources.domain.models import EvidenceContent, IngestedSource, SourceProfile

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, MutableMapping

type NotebookValue = (
    Artifact
    | BatchIngestionResult
    | BundleValidation
    | Candidate
    | ChangeSet
    | ConfigurationReport
    | Definition
    | DiscoveryResult
    | DomainModelBundle
    | EvidenceContent
    | IngestedSource
    | Page[Definition]
    | Page[ReviewCase]
    | ProjectionAssessment
    | Publication
    | Readiness
    | ReferencePack
    | ReviewCase
    | ReviewImpact
    | SourceProfile
    | ValidationReport
)
type _Rows = tuple[tuple[str, str], ...]
type _Printer = Callable[..., object]
type _PrinterMap = MutableMapping[type[object], _Printer]
type _SourceValue = BatchIngestionResult | EvidenceContent | IngestedSource | SourceProfile
type _ReleaseValue = (
    BundleValidation | Candidate | ProjectionAssessment | Publication | Readiness | ValidationReport
)

_TYPES = (
    Artifact,
    BatchIngestionResult,
    BundleValidation,
    Candidate,
    ChangeSet,
    Concept,
    ConfigurationReport,
    Definition,
    DiscoveryResult,
    DomainModelBundle,
    EvidenceContent,
    IngestedSource,
    Page,
    ProjectionAssessment,
    Publication,
    Readiness,
    ReferencePack,
    ReviewCase,
    ReviewImpact,
    SourceProfile,
    ValidationReport,
)
_MAX_TEXT = 180
_MAX_DEFINITIONS = 8


class NotebookRenderer(Protocol, metaclass=ABCMeta):
    """Render an inspected value without acquiring resources or changing state."""

    @abstractmethod
    def html(self, *, value: NotebookValue) -> str:
        """Return escaped, bounded HTML for the supplied snapshot."""
        ...


def _label(value: str) -> str:
    bounded = "".join(
        character if character.isprintable() else " " for character in value[:_MAX_TEXT]
    )
    return bounded if len(value) <= _MAX_TEXT else bounded + "…"


def _bundle_rows(*, bundle: DomainModelBundle) -> _Rows:
    definitions = bundle.content.definitions
    return (
        ("Release", bundle.version),
        ("Publisher", bundle.approval.actor),
        ("Definitions", str(len(definitions))),
        ("First definitions", ", ".join(item.name for item in definitions[:_MAX_DEFINITIONS])),
    )


def _review_rows(*, value: ReviewCase | ReviewImpact | ChangeSet) -> _Rows:
    if isinstance(value, ReviewCase):
        return (
            ("Review case", value.id.value),
            ("Case version", str(value.version)),
            ("Status", value.status.value),
            ("Reason", value.reason),
        )
    if isinstance(value, ReviewImpact):
        return (
            ("Workspace revision", str(value.workspace_revision)),
            ("Proposed changes", str(len(value.definition_changes))),
            ("Blockers", str(len(value.blockers))),
        )
    return (
        ("Comparison", value.comparison.value),
        ("Compatibility", value.compatibility.value),
        ("Changes", str(len(value.changes))),
    )


def _release_rows(*, value: _ReleaseValue) -> _Rows:
    if isinstance(value, Candidate):
        return (
            ("Candidate", value.id.value),
            ("Workspace revision", str(value.workspace_revision)),
            ("Definitions", str(len(value.content.definitions))),
        )
    if isinstance(value, Publication):
        return (
            ("Publication", value.id.value),
            ("Candidate hash", value.candidate.content_hash.value),
            ("Ready", str(value.ready)),
            ("Checks", str(len(value.checks))),
            ("Blockers", str(len(value.blockers))),
            ("First check", value.checks[0].message if value.checks else "No recorded checks"),
        )
    if isinstance(value, Readiness):
        return (
            ("Candidate hash", value.candidate_hash.value),
            ("Ready", str(value.ready)),
            ("Checks", str(len(value.checks))),
            ("Blockers", str(len(value.blockers))),
        )
    if isinstance(value, ValidationReport):
        return (
            ("Validation", value.id.value),
            ("Candidate", value.candidate_id.value),
            ("Issues", str(len(value.issues))),
            ("Acceptance results", str(len(value.acceptance))),
        )
    if isinstance(value, ProjectionAssessment):
        return (
            ("Release", value.model.version),
            ("Release hash", value.model.content_hash.value),
            ("Availability", value.availability.value),
            ("Projection findings", str(len(value.findings))),
            ("Consumer obligations", str(len(value.consumer_obligations))),
        )
    return (
        ("Valid", str(value.valid)),
        ("Schema version", value.schema_version),
        ("Issues", str(len(value.issues))),
    )


def _source_rows(*, value: _SourceValue) -> _Rows:
    if isinstance(value, BatchIngestionResult):
        successes = sum(isinstance(item, IngestionSuccess) for item in value.items)
        return (
            ("Selections processed", str(len(value.items))),
            ("Succeeded", str(successes)),
            ("Failed", str(len(value.items) - successes)),
        )
    if isinstance(value, IngestedSource):
        return (
            ("Source", value.revision.source_id.value),
            ("Exact revision", value.revision.revision_id.value),
            ("Evidence records", str(len(value.evidence))),
            ("Retained original", str(value.retained_original is not None)),
        )
    if isinstance(value, SourceProfile):
        return (
            ("Exact revision", value.source.revision_id.value),
            ("Parser", value.processing.parser_id),
            ("Pages", "Unknown" if value.page_count is None else str(value.page_count)),
            ("Tables", str(len(value.tables))),
            ("Issues", str(len(value.issues))),
        )
    return (
        ("Evidence", value.evidence.id.value),
        ("Exact revision", value.evidence.source.revision_id.value),
        ("Locator", type(value.evidence.locator).__name__),
        ("Parser", value.evidence.processing.parser_id),
    )


def _detail_rows(
    *, value: Artifact | ConfigurationReport | Definition | DiscoveryResult | ReferencePack
) -> _Rows:
    if isinstance(value, Definition):
        return (
            ("Definition", value.name),
            ("Label", value.display_name),
            ("Kind", value.kind.value),
            ("Revision", str(value.revision)),
            ("Meaning", value.meaning),
            ("Recorded citations", str(len(value.evidence))),
        )
    if isinstance(value, ConfigurationReport):
        return (
            ("Configuration source", value.source.value),
            ("Schema setup", value.database_initialization.value),
            ("Integrations", ", ".join(value.integrations[:_MAX_DEFINITIONS])),
        )
    if isinstance(value, Artifact):
        return (
            ("Store", value.store),
            ("Artifact key", value.key),
            ("Content hash", value.content_hash.value),
        )
    if isinstance(value, DiscoveryResult):
        return (
            ("Discovery", value.id.value),
            ("Run version", str(value.version)),
            ("Status", value.status.value),
            ("Source failures", str(len(value.failures))),
        )
    return (
        ("Reference pack", value.title),
        ("Version", value.pin.version),
        ("Content hash", value.pin.content_hash.value),
        ("Definitions", str(len(value.definitions))),
    )


def _rows(*, value: NotebookValue) -> _Rows:
    if isinstance(value, Page):
        return (
            ("Items", str(len(value.items))),
            ("More results available", str(value.next_cursor is not None)),
            *(
                (f"Item {number}", item.name if isinstance(item, Definition) else item.id.value)
                for number, item in enumerate(value.items[:_MAX_DEFINITIONS], start=1)
            ),
        )
    if isinstance(value, (ReviewCase, ReviewImpact, ChangeSet)):
        return _review_rows(value=value)
    if isinstance(value, DomainModelBundle):
        return _bundle_rows(bundle=value)
    if isinstance(value, (BatchIngestionResult, EvidenceContent, IngestedSource, SourceProfile)):
        return _source_rows(value=value)
    if isinstance(
        value,
        (
            BundleValidation,
            Candidate,
            ProjectionAssessment,
            Publication,
            Readiness,
            ValidationReport,
        ),
    ):
        return _release_rows(value=value)
    return _detail_rows(value=value)


def render_notebook(*, value: NotebookValue, renderer: NotebookRenderer | None = None) -> str:
    """Render a supplied SDK snapshot as a small accessible table."""
    if renderer is not None:
        return renderer.html(value=value)
    caption = escape(type(value).__name__)
    lines = "".join(
        f'<tr><th scope="row">{escape(label)}</th><td>{escape(_label(item))}</td></tr>'
        for label, item in _rows(value=value)
    )
    return f"<table><caption>{caption}</caption><tbody>{lines}</tbody></table>"


@runtime_checkable
class _Formatter(Protocol):
    @property
    def type_printers(self) -> _PrinterMap: ...


@runtime_checkable
class _Display(Protocol):
    @property
    def formatters(self) -> Mapping[str, object]: ...


@runtime_checkable
class _Shell(Protocol):
    @property
    def display_formatter(self) -> object: ...


@runtime_checkable
class _ShellAccessor(Protocol):
    def __call__(self) -> object: ...


class _PlainPrinter(Protocol):
    def text(self, text: str, /) -> None: ...


@dataclass(frozen=True, kw_only=True)
class _Registration:
    registry: _PrinterMap
    previous: dict[type[object], _Printer]
    printer: _Printer

    def restore(self) -> None:
        for kind in _TYPES:
            if self.registry.get(kind) is self.printer:
                if kind in self.previous:
                    self.registry[kind] = self.previous[kind]
                else:
                    del self.registry[kind]


_REGISTRATIONS: dict[int, tuple[_Registration, ...]] = {}


def _current_display() -> _Display:
    try:
        ipython = import_module("IPython")
    except ModuleNotFoundError:
        raise MissingCapabilityError(message="Install the optional notebook environment") from None
    accessor: object = getattr(ipython, "get_ipython", None)
    if isinstance(accessor, _ShellAccessor):
        shell = accessor()
        if isinstance(shell, _Shell) and isinstance(display := shell.display_formatter, _Display):
            return display
    raise MissingCapabilityError(message="Enable SDK display inside an active IPython kernel")


def _registry(*, display: _Display, mime: str) -> _PrinterMap:
    formatter = display.formatters.get(mime)
    if not isinstance(formatter, _Formatter):
        raise MissingCapabilityError(message="Open a kernel with standard IPython formatters")
    return formatter.type_printers


def enable_notebook_display(*, renderer: NotebookRenderer | None = None) -> None:
    """Install repeat-safe formatters in the current kernel on explicit request."""
    display = _current_display()
    key = id(display)
    if key in _REGISTRATIONS:
        return

    def rich(value: NotebookValue, /) -> str:
        return render_notebook(value=value, renderer=renderer)

    def plain(
        value: NotebookValue,
        printer: _PlainPrinter,
        _cycle: bool,  # noqa: FBT001 - Match the IPython formatter callback signature.
        /,
    ) -> None:
        rows = (f"{label}: {_label(item)}" for label, item in _rows(value=value))
        printer.text(f"{type(value).__name__}\n" + "\n".join(rows))

    registrations = tuple(
        _Registration(
            registry=registry,
            previous={kind: registry[kind] for kind in _TYPES if kind in registry},
            printer=printer,
        )
        for mime, printer in (("text/html", rich), ("text/plain", plain))
        for registry in (_registry(display=display, mime=mime),)
    )
    for registration in registrations:
        registration.registry.update(dict.fromkeys(_TYPES, registration.printer))
    _REGISTRATIONS[key] = registrations


def disable_notebook_display() -> None:
    """Restore existing formatters for the current kernel."""
    if not _REGISTRATIONS:
        return
    for registration in _REGISTRATIONS.pop(id(_current_display()), ()):
        registration.restore()
