"""Publication guards over immutable release and authorization records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.snapshots import Approval, Publication
from domain_kernel.shared.errors import ScopeMismatchError, StaleStateError

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.snapshots import Candidate


__all__ = ["Approval", "Publication", "require_current_publication"]


def require_current_publication(
    *,
    publication: Publication,
    current: Candidate,
    policy_fingerprint: str,
) -> None:
    """Require unchanged workspace, review state and rules at authorization."""
    if publication.scope != current.scope:
        raise ScopeMismatchError
    stored = publication.candidate
    if (
        current.workspace_revision != stored.workspace_revision
        or current.review_snapshot_version != stored.review_snapshot_version
        or current.review_snapshot_hash != stored.review_snapshot_hash
        or current.content_hash != stored.content_hash
        or policy_fingerprint != publication.policy_fingerprint
    ):
        raise StaleStateError(message="Prepare and inspect a fresh publication for this workspace")
