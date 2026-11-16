from __future__ import annotations

import pytest

from domain_kernel import (
    AlignmentId,
    AlignmentSuggestionId,
    ApprovalId,
    AttributeId,
    BundleId,
    CandidateId,
    ChangePlanId,
    ContentHash,
    DecisionId,
    DefinitionId,
    DiscoveryDraftId,
    DiscoveryRunId,
    EvidenceId,
    KeyId,
    MappingId,
    ModelId,
    ObligationId,
    PageCursor,
    PatternId,
    PersonId,
    ProjectId,
    ProposalId,
    PublicationId,
    QuestionId,
    ReferenceDefinitionId,
    ReviewCaseId,
    SourceId,
    SourceRevisionId,
    ValidationReportId,
)
from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


class StringSubclass(str):
    """String subclass used to check exact-string validation."""

    __slots__: tuple[str, ...] = ()


IDENTIFIER_TYPES: tuple[type[OpaqueIdentifier], ...] = (
    AlignmentId,
    AlignmentSuggestionId,
    ApprovalId,
    AttributeId,
    BundleId,
    CandidateId,
    ChangePlanId,
    ContentHash,
    DecisionId,
    DefinitionId,
    DiscoveryDraftId,
    DiscoveryRunId,
    EvidenceId,
    KeyId,
    MappingId,
    ModelId,
    ObligationId,
    OpaqueIdentifier,
    PageCursor,
    PatternId,
    PersonId,
    ProjectId,
    ProposalId,
    PublicationId,
    QuestionId,
    ReferenceDefinitionId,
    ReviewCaseId,
    SourceId,
    SourceRevisionId,
    ValidationReportId,
)


@pytest.mark.parametrize("identifier_type", IDENTIFIER_TYPES)
def test_identifier_types_accept_positional_and_keyword_values(
    identifier_type: type[OpaqueIdentifier],
) -> None:
    value = (
        f"sha256:{'a' * 64}" if identifier_type in (ContentHash, SourceRevisionId) else "value-1"
    )

    assert identifier_type(value).value == value
    assert identifier_type(value=value).value == value


@pytest.mark.parametrize("identifier_type", IDENTIFIER_TYPES)
@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "Identifier cannot be empty"),
        (" leading", "Identifier cannot contain surrounding whitespace"),
        ("trailing ", "Identifier cannot contain surrounding whitespace"),
    ],
)
def test_identifier_types_reject_empty_or_trimmed_values(
    identifier_type: type[OpaqueIdentifier],
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _ = identifier_type(value)


@pytest.mark.parametrize("identifier_type", IDENTIFIER_TYPES)
def test_identifier_types_reject_str_subclasses(
    identifier_type: type[OpaqueIdentifier],
) -> None:
    value = (
        f"sha256:{'a' * 64}" if identifier_type in (ContentHash, SourceRevisionId) else "value-1"
    )

    with pytest.raises(TypeError):
        _ = identifier_type(StringSubclass(value))


@pytest.mark.parametrize("identifier_type", IDENTIFIER_TYPES)
def test_identifier_types_reject_non_string_values(
    identifier_type: type[OpaqueIdentifier],
) -> None:
    with pytest.raises(TypeError, match="Identifier must be a string"):
        _ = identifier_type(17)  # pyright: ignore[reportArgumentType] -- runtime boundary validation


def test_different_identifier_types_are_nominally_distinct() -> None:
    definition_id = DefinitionId("same-value")
    review_case_id = ReviewCaseId("same-value")

    assert definition_id.value == review_case_id.value
    assert definition_id != review_case_id


def test_identifier_equality_and_hashing_are_stable_within_a_type() -> None:
    first = ReviewCaseId("case-1")
    second = ReviewCaseId(value="case-1")

    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


@pytest.mark.parametrize(
    "identifier_type",
    [ContentHash, SourceRevisionId],
)
def test_hash_identifiers_accept_sha256_values(
    identifier_type: type[OpaqueIdentifier],
) -> None:
    digest = f"sha256:{'a' * 64}"

    assert identifier_type(digest).value == digest


@pytest.mark.parametrize(
    "value",
    ["sha256:", "sha256:abc", f"sha256:{'A' * 64}", f"sha1:{'a' * 64}"],
)
@pytest.mark.parametrize("identifier_type", [ContentHash, SourceRevisionId])
def test_hash_identifiers_reject_malformed_sha256_values(
    identifier_type: type[OpaqueIdentifier],
    value: str,
) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        _ = identifier_type(value)


@pytest.mark.parametrize("value", ["@id", "@type", "rel:owns"])
def test_attribute_id_rejects_reserved_spellings(value: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        _ = AttributeId(value)


def test_attribute_id_accepts_an_ordinary_stable_key() -> None:
    assert AttributeId("asset_code").value == "asset_code"
