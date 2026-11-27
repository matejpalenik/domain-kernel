"""Check and retain role witnesses for a relationship inferred from one record."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from domain_kernel.discovery.application.evidence_binding import exact_quote
from domain_kernel.discovery.application.schema_evidence import Witness  # noqa: TC001 - Pydantic resolves the witness model at runtime.
from domain_kernel.discovery.application.schema_model import (
    _Record,  # pyright: ignore[reportPrivateUsage] -- Share the discovery response policy.
)
from domain_kernel.discovery.domain.bindings import BindingWitness
from domain_kernel.discovery.domain.schema_evidence import SchemaRecordBinding
from domain_kernel.sources.domain.parsed import CellRange

if TYPE_CHECKING:
    from domain_kernel.discovery.application.contracts.inference_input import InferenceInput

CAPTURE = """
Read each subject record as a whole. In scope, identify its subject, responsible or affected
roles, outcomes, and the items required or allowed at each stage. Look through labeled
subsections and header-to-row structure. Capture the relationship that the record establishes,
even when no single sentence states it. For an association assembled from separate fields,
provide a record_binding with a distinctive record anchor and exact source and target role
witnesses. Each must quote text unambiguously in its numbered passage. Include them among the
observation witnesses. Use null for meanings directly expressed by their own witness.
Use the reusable relationship appropriate to the evidenced scope and keep the record's
instance values as evidence. A section heading, shared page or adjacent field alone does
not establish that the roles belong to the same record. In a table use the same data row,
or provide an explicit quote that states a cross-record reference. Keep the subject and
roles of each record separate. Prefer relationships that connect the roles in the question
over incidental metadata about those roles.
"""

VERIFY = """
For each record_binding, independently check that the record anchor identifies the owning
record or row and that both quoted witnesses, in that order, belong to that record with the
stated roles. Compare sibling headings, enclosing section and field labels, and row boundaries.
Reject a join that requires unrelated records or a narrower section with a different subject.
Check the proposed relationship separately from co-membership. Being in the same record
does not by itself imply selection, causation, identity, or any other specific predicate.
If a claim combines separate fields without a record binding, require a direct witness that
expresses the association or mark it insufficient.
"""


class RecordLink(_Record):
    """Exact evidence for the owning record and each role occurrence."""

    anchor: Witness
    source: Witness
    target: Witness


def _witness(*, item: Witness, inputs: tuple[InferenceInput, ...]) -> BindingWitness | None:
    if not 1 <= item.citation <= len(inputs) or not item.quote.strip():
        return None
    part = inputs[item.citation - 1]
    if len(part.evidence) != 1:
        return None
    quote = (
        item.quote
        if part.text.count(item.quote) == 1
        else exact_quote(text=part.text, quote=item.quote)
    )
    if quote is None:
        return None
    return BindingWitness(evidence=part.evidence[0], quote=quote)


def _row(*, witness: BindingWitness) -> tuple[str, str] | None:
    locator = witness.evidence.locator
    if not isinstance(locator, CellRange):
        return None
    rows = set(re.findall(r"[0-9]+", locator.cells))
    return (locator.sheet, next(iter(rows))) if len(rows) == 1 else None


def _same_table_row(*, link: RecordLink, inputs: tuple[InferenceInput, ...]) -> bool:
    parts = (link.anchor, link.source, link.target)
    if len({item.citation for item in parts}) != 1:
        return False
    text = inputs[link.anchor.citation - 1].text
    return any(all(item.quote in line for item in parts) for line in text.splitlines())


def bind(*, link: RecordLink, inputs: tuple[InferenceInput, ...]) -> SchemaRecordBinding | None:
    """Bind one within-record link, rejecting inexact, cross-revision and cross-row roles."""
    anchor = _witness(item=link.anchor, inputs=inputs)
    source = _witness(item=link.source, inputs=inputs)
    target = _witness(item=link.target, inputs=inputs)
    if anchor is None or source is None or target is None or source == target:
        return None
    witnesses = (anchor, source, target)
    if len({item.evidence.source for item in witnesses}) != 1:
        return None
    if any(
        isinstance(item.evidence.locator, CellRange) or inputs[mention.citation - 1].is_table
        for item, mention in zip(witnesses, (link.anchor, link.source, link.target), strict=True)
    ):
        rows = {_row(witness=item) for item in witnesses}
        if (None in rows or len(rows) != 1) and not _same_table_row(link=link, inputs=inputs):
            return None
    return SchemaRecordBinding(anchor=anchor, source=source, target=target)
