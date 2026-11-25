"""Durable operations that receive their own attribution."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class AuditAction(StrEnum):
    """Durable operations that receive their own attribution."""

    CREATE_PROJECT = "create_project"
    CREATE_MODEL = "create_model"
    INGEST_SOURCE = "ingest_source"
    INGEST_SOURCE_REVISION = "ingest_source_revision"
    CAPTURE_SOURCE_MANIFEST = "capture_source_manifest"
    PROFILE_SOURCE = "profile_source"
    COPY_SOURCE_ORIGINAL = "copy_source_original"
    DISCOVER = "discover"
    EXTRACT_PROPOSALS = "extract_proposals"
    RESUME_DISCOVERY = "resume_discovery"
    PROPOSE_ALIGNMENT = "propose_alignment"
    PROPOSE_CHANGE = "propose_change"
    REOPEN_REVIEW_CASE = "reopen_review_case"
    DECIDE_REVIEW = "decide_review"
    COMPILE = "compile"
    VALIDATE = "validate"
    PREPARE_PUBLICATION = "prepare_publication"
    PUBLISH = "publish"
    EXPORT = "export"
