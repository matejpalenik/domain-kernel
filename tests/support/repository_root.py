"""Locate the checkout for tests that inspect repository-owned files."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
