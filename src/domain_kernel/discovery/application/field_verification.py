"""Match field verdicts to stable claim identities and fail closed on unsupported dimensions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.discovery.application.claim_extraction import Assessment

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from domain_kernel.discovery.application.claim_extraction import (
        Anchor,
        FieldDecision,
        IdentifiedClaim,
        Verdict,
    )


def assess(
    *,
    claim: IdentifiedClaim,
    votes: Sequence[Verdict],
    stage: str,
    resolve: Callable[[Anchor], Anchor | None],
) -> Assessment:
    """Validate cited field decisions before combining them into a semantic outcome."""
    matches = [v for v in votes if v.claim_id == claim.claim_id]
    result = Assessment(
        stage=stage,
        claim_id=claim.claim_id,
        meaning=claim.meaning,
        verdict=None,
        status="invalid",
        detail="Missing or duplicate verdict for the supplied claim ID.",
    )
    if len(matches) != 1:
        return result
    vote = matches[0].model_copy(deep=True)
    statuses: dict[str, list[str]] = {}
    fields = (
        ("meaning", vote.meaning, True),
        ("actor", vote.actor, claim.kind == "relationship"),
        ("object", vote.object, claim.kind == "relationship"),
        ("recipient", vote.recipient, False),
        ("modality", vote.modality, False),
        ("conditions", vote.conditions, bool(claim.conditions)),
        ("exceptions", vote.exceptions, bool(claim.exceptions)),
    )
    resolved_fields: dict[str, FieldDecision] = {}
    for name, field, required in fields:
        if field.evidence is not None:
            checked = resolve(field.evidence)
            if checked is None:
                result.detail = f"Unresolvable quotation for {name}."
                return result
            resolved_fields[name] = field.model_copy(update={"evidence": checked})
        if field.status == "not_applicable" and (required or field.evidence is not None):
            result.detail = f"Inapplicable verdict for a material or cited field: {name}."
            return result
        if field.evidence is None and field.status not in ("not_applicable", "insufficient"):
            result.detail = f"Missing decisive quotation for {name}."
            return result
        statuses.setdefault(field.status, []).append(name)
    result.verdict = vote.model_copy(update=resolved_fields)
    for status in ("contradicted", "insufficient", "partly_supported"):
        if status in statuses:
            result.status = status
            result.detail = f"{status}: {', '.join(statuses[status])}. {vote.reason}"
            return result
    result.status = "supported"
    result.detail = vote.reason
    return result
