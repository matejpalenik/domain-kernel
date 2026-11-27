"""Verify immutable reference-pack composition and independent loading."""

from dataclasses import replace

import pytest

from domain_kernel import (
    BusinessCode,
    InvalidReferencePackError,
    LabelText,
    MeaningText,
    ObligationId,
    ObligationKind,
    Pattern,
    PatternNotFoundError,
    ReferenceDefinition,
    ReferenceDefinitionId,
    ReferencePack,
    ReferencePackImport,
    ReferencePackObligation,
    ReferencePackSpec,
    UnitDefinition,
    UnsupportedReferencePackVersionError,
    ValueSetDefinition,
    ValueSetMember,
    ValueSetMembership,
)
from domain_kernel.shared.hashing import Hashing


def _spec(**details: object) -> ReferencePackSpec:
    defaults = ReferencePackSpec(
        key="example.local-duration",
        version="1.0.0",
        title="Local duration",
        applicability="Reused units for a recruitment application.",
        provenance="Authored specification",
        license="Apache-2.0",
    )
    return replace(defaults, **details)


@pytest.fixture
def published_pack() -> ReferencePack:
    hour = ReferenceDefinition(
        id=ReferenceDefinitionId(value="hour"),
        name="hour",
        meaning="Elapsed hour.",
        body=UnitDefinition(symbol="h"),
        provenance="Local application choice",
    )
    units = ReferenceDefinition(
        id=ReferenceDefinitionId(value="duration-units"),
        name="duration-units",
        meaning="Allowed units.",
        body=ValueSetDefinition(
            membership=ValueSetMembership.CLOSED,
            members=[
                ValueSetMember(
                    code=BusinessCode(value="h"),
                    label=LabelText(value="Hour"),
                    meaning=MeaningText(value="Local elapsed hour."),
                    unit=hour.id,
                )
            ],
        ),
        provenance="Local application choice",
    )
    pattern = Pattern(
        display_name="Duration vocabulary",
        description="Reuse the local duration unit.",
        definitions=[hour, units],
        entrypoint_ids=[units.id],
    )
    obligation = ReferencePackObligation(
        id=ObligationId(value="inspect-units"),
        description="Inspect duration unit usage.",
        kind=ObligationKind.COVERAGE,
        required=True,
        reference_ids=[units.id],
        validator_id="unit-review",
    )
    build = ReferencePack.compose(
        spec=_spec(definitions=[hour, units], patterns=[pattern], obligations=[obligation]),
        actor="author",
        reason="Review the authored reference materials.",
    )
    assert build.validation.valid
    assert build.pack is not None
    assert pattern.reference_pack is None
    return build.pack


def test_compose_remaps_the_unit_edge_and_preserves_the_omitted_obligation(
    published_pack: ReferencePack,
) -> None:
    original = published_pack.get_pattern(name="duration-vocabulary")
    build = ReferencePack.compose(
        spec=_spec(
            key="example.recruitment",
            imports=[
                ReferencePackImport(
                    reference_pack=published_pack,
                    namespace="shared",
                    pattern_ids=[original.id],
                    obligation_ids=[],
                )
            ],
        ),
        actor="author",
        reason="Use the vocabulary without importing its obligations.",
    )
    assert build.validation.valid
    assert build.pack is not None
    restored = ReferencePack.deserialize(payload=build.pack.serialize())
    assert restored.validate() == build.validation
    assert restored.composition is not None
    assert restored.composition.imports[0].omitted_obligations == published_pack.obligations
    assert not restored.obligations
    pattern = restored.get_pattern(name=original.name)
    assert pattern.name == original.name
    assert pattern.id.value == f"shared:{original.id.value}"
    assert pattern.reference_pack == restored.pin
    units = next(item for item in pattern.definitions if item.name == "duration-units")
    assert isinstance(units.body, ValueSetDefinition)
    assert units.body.members[0].unit == ReferenceDefinitionId(value="shared:hour")
    assert units.origins[0].reference_pack == published_pack.pin
    assert units.reference_pack == restored.pin
    assert original.reference_pack == published_pack.pin


def test_duplicate_pattern_names_are_diagnostics(published_pack: ReferencePack) -> None:
    original = published_pack.get_pattern(name="duration-vocabulary")
    imports = [
        ReferencePackImport(
            reference_pack=published_pack,
            namespace=namespace,
            pattern_ids=[original.id],
            obligation_ids=[],
        )
        for namespace in ("local", "other")
    ]
    build = ReferencePack.compose(
        spec=_spec(key="example.duplicate", imports=imports),
        actor="author",
        reason="Inspect the conflicting names.",
    )
    assert build.pack is None
    assert any(issue.code == "duplicate_pattern_name" for issue in build.validation.issues)


def test_pack_lookup_and_codec_fail_closed(published_pack: ReferencePack) -> None:
    original = published_pack.get_pattern(name="duration-vocabulary")
    assert published_pack.get_pattern(pattern_id=original.id) == original
    with pytest.raises(PatternNotFoundError):
        _ = published_pack.get_pattern(name=original.display_name)
    with pytest.raises(ValueError, match="exactly one"):
        _ = published_pack.get_pattern(name=original.name, pattern_id=original.id)
    payload = published_pack.serialize()
    assert (
        ReferencePack.deserialize(
            payload=payload, expected_hash=Hashing.hash_bytes(content=payload)
        )
        == published_pack
    )
    with pytest.raises(InvalidReferencePackError):
        _ = ReferencePack.deserialize(payload=payload.replace(b'"Local duration"', b'"Altered"'))
    with pytest.raises(UnsupportedReferencePackVersionError):
        _ = ReferencePack.get_json_schema(schema_version="2")


def test_conflicting_releases_of_one_dependency_key_fail(published_pack: ReferencePack) -> None:
    same_label = ReferencePack.compose(
        spec=_spec(title="An alternative release"),
        actor="author",
        reason="Different content under the same catalog version.",
    )
    assert same_label.pack is not None
    assert same_label.pack.pin.content_hash != published_pack.pin.content_hash
    combined = ReferencePack.compose(
        spec=_spec(
            key="example.conflict",
            imports=[
                ReferencePackImport(
                    reference_pack=published_pack, namespace="source", obligation_ids=[]
                ),
                ReferencePackImport(
                    reference_pack=same_label.pack, namespace="alternate", obligation_ids=[]
                ),
            ],
        ),
        actor="author",
        reason="Inspect dependency release conflict.",
    )
    assert combined.pack is None
    assert any(issue.code == "dependency_conflict" for issue in combined.validation.issues)


def test_dangling_unit_edge_returns_structured_issues(published_pack: ReferencePack) -> None:
    units = next(item for item in published_pack.definitions if item.name == "duration-units")
    build = ReferencePack.compose(
        spec=_spec(definitions=[units]),
        actor="author",
        reason="Check graph closure.",
    )
    assert build.pack is None
    assert any(issue.code == "unresolved_shape_reference" for issue in build.validation.issues)
