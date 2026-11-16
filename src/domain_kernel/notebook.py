"""Bounded, optional rendering of inspected SDK values."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from html import escape
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel._shared.domain.changes import ChangeSet
from domain_kernel._shared.domain.definitions import Concept, Definition
from domain_kernel.bundles import DomainModelBundle
from domain_kernel.modeling.domain.publications import Publication
from domain_kernel.modeling.domain.snapshots import Candidate, ValidationReport
from domain_kernel.review.domain.models import ReviewCase, ReviewImpact
from domain_kernel.shared.errors import MissingCapabilityError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, MutableMapping

type NotebookValue = (
    Candidate
    | ChangeSet
    | Definition
    | DomainModelBundle
    | Publication
    | ReviewCase
    | ReviewImpact
    | ValidationReport
)
type _Rows = tuple[tuple[str, str], ...]
type _Printer = Callable[..., object]
type _PrinterMap = MutableMapping[type[object], _Printer]

_TYPES = (
    Candidate,
    ChangeSet,
    Concept,
    Definition,
    DomainModelBundle,
    Publication,
    ReviewCase,
    ReviewImpact,
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
    return value if len(value) <= _MAX_TEXT else value[:_MAX_TEXT] + "…"


def _release_rows(*, bundle: DomainModelBundle) -> _Rows:
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


def _rows(*, value: NotebookValue) -> _Rows:
    if isinstance(value, DomainModelBundle):
        return _release_rows(bundle=value)
    if isinstance(value, Definition):
        return (
            ("Definition", value.name),
            ("Label", value.display_name),
            ("Kind", value.kind.value),
            ("Revision", str(value.revision)),
            ("Meaning", value.meaning),
        )
    if isinstance(value, Candidate):
        return (
            ("Candidate", value.id.value),
            ("Workspace revision", str(value.workspace_revision)),
            ("Definitions", str(len(value.content.definitions))),
        )
    if isinstance(value, Publication):
        return (
            ("Publication", value.id.value),
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
    return _review_rows(value=value)


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
