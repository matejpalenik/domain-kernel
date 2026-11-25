"""Check equivalent graph paths against the procurement benchmark scorer."""

import pytest

from benchmarks.procurement_data import Fixture, Slot
from benchmarks.procurement_score import (
    Blind,
    CheckBinding,
    Grade,
    Proposal,
    Review,
    fixture_passes,
)

pytestmark = pytest.mark.integration


def test_archive_shelf_inverse_answers_the_same_question() -> None:
    pytest.importorskip("rdflib")
    box = Proposal(id="box", kind="concept", title="Archive box", meaning="Stored archive unit.")
    shelf = Proposal(id="shelf", kind="concept", title="Shelf", meaning="Storage location.")
    stored = Proposal(
        id="edge",
        kind="relationship",
        title="Holds",
        meaning="A shelf holds an archive box.",
        source="shelf",
        target="box",
    )
    review = Review(
        reviewer="fixture-review",
        grades=(
            Grade(proposal="box", verdict="match", target="box"),
            Grade(proposal="shelf", verdict="match", target="shelf"),
            Grade(proposal="edge", verdict="extension", target="holds"),
        ),
    )
    inverse = Fixture(
        id="shelf-lookup-inverse",
        question="where-stored",
        modelet="archive-storage",
        alternative_group="find-shelf",
        slots=(
            Slot(name="box", kind="concept", target="box"),
            Slot(name="shelf", kind="concept", target="shelf"),
            Slot(name="relation", kind="relationship", target="holds", endpoints=("shelf", "box")),
        ),
        graph="<urn:test:s9> {{relation}} <urn:test:box1> .",
        query="SELECT ?shelf WHERE { ?shelf {{relation}} <urn:test:box1> . }",
        expected=(("urn:test:s9",),),
    )
    binding = CheckBinding(
        fixture=inverse.id, slots={"shelf": "shelf", "box": "box", "relation": "edge"}
    )
    blind = Blind(id="archive", proposals=(box, shelf, stored))
    assert fixture_passes(fixture=inverse, binding=binding, review=review, blind=blind)
    reversed_edge = stored.model_copy(update={"source": "box", "target": "shelf"})
    assert not fixture_passes(
        fixture=inverse,
        binding=binding,
        review=review,
        blind=blind.model_copy(update={"proposals": (box, shelf, reversed_edge)}),
    )


def test_transit_route_can_answer_through_a_service_pattern() -> None:
    pytest.importorskip("rdflib")
    proposals = (
        Proposal(id="route", kind="concept", title="Route", meaning="Scheduled service."),
        Proposal(id="pattern", kind="concept", title="Pattern", meaning="A route's stop pattern."),
        Proposal(id="stop", kind="concept", title="Stop", meaning="A boarding location."),
        Proposal(
            id="uses",
            kind="relationship",
            title="Uses pattern",
            meaning="A route uses a stop pattern.",
            source="route",
            target="pattern",
        ),
        Proposal(
            id="visits",
            kind="relationship",
            title="Visits stop",
            meaning="A pattern visits a stop.",
            source="pattern",
            target="stop",
        ),
    )
    review = Review(
        reviewer="fixture-review",
        grades=tuple(
            Grade(
                proposal=row.id,
                verdict="match" if row.kind == "concept" else "extension",
                target=row.id,
            )
            for row in proposals
        ),
    )
    path = Fixture(
        id="route-stops-through-pattern",
        question="which-stops",
        modelet="transit",
        alternative_group="stops-on-route",
        slots=(
            Slot(name="route", kind="concept", target="route"),
            Slot(name="pattern", kind="concept", target="pattern"),
            Slot(name="stop", kind="concept", target="stop"),
            Slot(name="uses", kind="relationship", target="uses", endpoints=("route", "pattern")),
            Slot(
                name="visits", kind="relationship", target="visits", endpoints=("pattern", "stop")
            ),
        ),
        graph=(
            "<urn:test:r1> {{uses}} <urn:test:p1> .\n"
            "<urn:test:p1> {{visits}} <urn:test:stop1> .\n"
            "<urn:test:p2> {{visits}} <urn:test:stop2> ."
        ),
        query="SELECT ?stop WHERE { <urn:test:r1> {{uses}}/{{visits}} ?stop . }",
        expected=(("urn:test:stop1",),),
    )
    binding = CheckBinding(fixture=path.id, slots={row.id: row.id for row in proposals})
    blind = Blind(id="transit", proposals=proposals)
    assert fixture_passes(fixture=path, binding=binding, review=review, blind=blind)
    overbroad = path.model_copy(update={"query": "SELECT ?stop WHERE { ?p {{visits}} ?stop . }"})
    assert not fixture_passes(fixture=overbroad, binding=binding, review=review, blind=blind)
