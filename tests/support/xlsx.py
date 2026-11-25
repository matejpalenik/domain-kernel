"""Typed access to the optional workbook writer used by source fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from io import BytesIO


class WritableSheet(Protocol):
    """Worksheet supporting fixture rows."""

    def append(self, values: tuple[str | int, ...], /) -> None:
        """Append a row of fixture cells."""
        ...


class WritableWorkbook(Protocol):
    """Workbook supporting fixture sheets and in-memory serialization."""

    def create_sheet(self, *, title: str) -> WritableSheet:
        """Create a named fixture sheet."""
        ...

    def save(self, *, filename: BytesIO) -> None:
        """Serialize the workbook to a byte buffer."""
        ...


@runtime_checkable
class ExcelWriter(Protocol):
    """Openpyxl module interface used by fixtures."""

    def Workbook(self) -> WritableWorkbook:  # noqa: N802 - Openpyxl constructor.
        """Create an empty workbook."""
        ...
