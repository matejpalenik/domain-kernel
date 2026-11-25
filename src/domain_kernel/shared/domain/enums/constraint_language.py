"""Representation of a recorded constraint."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class ConstraintLanguage(StrEnum):
    """Representation of a recorded constraint."""

    TEXT = "text"
    JSON_SCHEMA = "json_schema"
    SHACL = "shacl"
