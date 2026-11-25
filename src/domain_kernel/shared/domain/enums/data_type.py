"""Scalar and reference categories used by business definitions."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class DataType(StrEnum):
    """Scalar and reference categories used by business definitions."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    REFERENCE = "reference"
