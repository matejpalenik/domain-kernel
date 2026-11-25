"""Test role witnesses against actual record boundaries."""

from dataclasses import replace

from domain_kernel.discovery.application.schema_evidence import Witness
from domain_kernel.discovery.application.schema_records import RecordLink, bind
from domain_kernel.sources.domain.parsed import CellRange
from tests.support.discovery import make_request


def test_shared_table_does_not_join_different_rows() -> None:
    text = "Permit | Reviewer\nP-17 | Lee\nP-18 | Patel"
    part = make_request(name="register", text=text, scope="Permits", arm="test").inputs[0]
    part = replace(
        part,
        is_table=True,
        evidence=(replace(part.evidence[0], locator=CellRange(sheet="Permits", cells="A1:B3")),),
    )
    link = RecordLink(
        anchor=Witness(citation=1, quote="P-17 | Lee"),
        source=Witness(citation=1, quote="P-17"),
        target=Witness(citation=1, quote="Lee"),
    )
    match = bind(link=link, inputs=(part,))
    assert match is not None
    assert match.target.quote == "Lee"
    wrong_row = link.model_copy(update={"target": Witness(citation=1, quote="Patel")})
    assert bind(link=wrong_row, inputs=(part,)) is None


def test_adjacent_quotes_cannot_join_different_source_revisions() -> None:
    permit = make_request(name="permit", text="Permit P-17", scope="Permits", arm="test").inputs[0]
    roster = make_request(name="roster", text="Reviewer Lee", scope="Permits", arm="test").inputs[0]
    link = RecordLink(
        anchor=Witness(citation=1, quote="Permit P-17"),
        source=Witness(citation=1, quote="P-17"),
        target=Witness(citation=2, quote="Reviewer Lee"),
    )
    assert bind(link=link, inputs=(permit, roster)) is None
