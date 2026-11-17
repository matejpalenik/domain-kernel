"""Immutable descriptions of observed table structure."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum, unique
from typing import TYPE_CHECKING

from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.sources.domain.parsed import CellValue, ParsedTable


@unique
class InferredColumnType(StrEnum):
    """Observed type of the non-null values in a column."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    MIXED = "mixed"
    UNKNOWN = "unknown"
    NULL = "null"


@dataclass(frozen=True, kw_only=True)
class ColumnProfile:
    """Descriptive column metadata for one capture."""

    name: str
    inferred_type: InferredColumnType
    nullable: bool
    identifier_candidate: bool
    provider_type_name: str | None = None

    def __post_init__(self) -> None:
        """Check the name and the observed metadata types."""
        require_text(value=self.name, field="Column name")
        require_exact(value=self.inferred_type, expected=InferredColumnType, field="Inferred type")
        require_exact(value=self.nullable, expected=bool, field="Nullable column")
        require_exact(value=self.identifier_candidate, expected=bool, field="Candidate identifier")
        if self.provider_type_name is not None:
            require_text(value=self.provider_type_name, field="Provider type name")


@dataclass(frozen=True, kw_only=True)
class TableProfile:
    """An observed table and its ordered column inventory."""

    name: str
    columns: Sequence[ColumnProfile]
    row_count: int

    def __post_init__(self) -> None:
        """Freeze the column inventory and validate its extent."""
        require_text(value=self.name, field="Table name")
        require_exact(value=self.row_count, expected=int, field="Table row count")
        columns = snapshot_sequence(items=self.columns, item_type=ColumnProfile, field="Columns")
        if (
            self.row_count < 0
            or not columns
            or len({item.name for item in columns}) != len(columns)
        ):
            raise ValueError("Use a nonnegative row count and distinct table columns")
        object.__setattr__(self, "columns", columns)


_TYPES = {
    str: InferredColumnType.STRING,
    int: InferredColumnType.INTEGER,
    Decimal: InferredColumnType.DECIMAL,
    float: InferredColumnType.FLOAT,
    bool: InferredColumnType.BOOLEAN,
    date: InferredColumnType.DATE,
    datetime: InferredColumnType.DATETIME,
}
_INTEGRAL = re.compile(r"[+-]?(?:0|[1-9][0-9]*)")
_DECIMAL = re.compile(r"[+-]?(?:0|[1-9][0-9]*)\.[0-9]+")


_ISO_DATE_LENGTH = 10


def _text_type(*, value: str) -> InferredColumnType:
    if _INTEGRAL.fullmatch(value):
        return InferredColumnType.INTEGER
    if _DECIMAL.fullmatch(value):
        return InferredColumnType.DECIMAL
    if value.casefold() in {"true", "false"}:
        return InferredColumnType.BOOLEAN
    if value[4:5] == "-" and value[7:8] == "-":
        try:
            if len(value) == _ISO_DATE_LENGTH:
                _ = date.fromisoformat(value)
                return InferredColumnType.DATE
            if value[10:11] in {"T", " "}:
                _ = datetime.fromisoformat(value)
                return InferredColumnType.DATETIME
        except ValueError:
            pass
    return InferredColumnType.STRING


def _observed_type(*, value: CellValue, text_scalars: bool) -> InferredColumnType:
    if value is None:
        return InferredColumnType.NULL
    if text_scalars and isinstance(value, str):
        return _text_type(value=value)
    return _TYPES[type(value)]


def _column_type(*, distinct: set[InferredColumnType], has_rows: bool) -> InferredColumnType:
    if not distinct:
        return InferredColumnType.NULL if has_rows else InferredColumnType.UNKNOWN
    if len(distinct) == 1:
        return next(iter(distinct))
    if distinct == {InferredColumnType.INTEGER, InferredColumnType.DECIMAL}:
        return InferredColumnType.DECIMAL
    return InferredColumnType.MIXED


def profile_table(*, table: ParsedTable, text_scalars: bool) -> TableProfile:
    """Profile rectangular evidence without assigning approved domain semantics."""
    columns: list[ColumnProfile] = []
    for position, heading in enumerate(table.columns):
        values = {(type(row[position]), row[position]) for row in table.rows}
        types = {
            _observed_type(value=row[position], text_scalars=text_scalars)
            for row in table.rows
            if row[position] is not None
        }
        nullable = (type(None), None) in values
        columns.append(
            ColumnProfile(
                name=heading,
                inferred_type=_column_type(distinct=types, has_rows=bool(table.rows)),
                nullable=nullable,
                identifier_candidate=bool(table.rows)
                and not nullable
                and len(values) == len(table.rows),
            ),
        )
    return TableProfile(name=table.name, columns=tuple(columns), row_count=len(table.rows))
