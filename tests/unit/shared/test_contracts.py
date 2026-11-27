from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from domain_kernel import Count, Issue, IssueSeverity, ModelKind, Page
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.application.results.page_cursor import PageCursor
from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.identifiers.content_hash import ContentHash

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference


def test_model_kind_exposes_observed_and_proposed_wire_values() -> None:
    assert {kind.name: kind.value for kind in ModelKind} == {
        "OBSERVED": "observed",
        "PROPOSED": "proposed",
    }


def test_count_accepts_nonnegative_exact_integers() -> None:
    assert Count(value=0).value == 0
    assert Count(value=1).value == 1


@pytest.mark.parametrize("value", [-1, -100])
def test_count_rejects_negative_values(value: int) -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        _ = Count(value=value)


@pytest.mark.parametrize("value", [1.0, "1"])
def test_count_rejects_non_integer_values(value: object) -> None:
    with pytest.raises(TypeError, match="exact integer"):
        _ = Count(value=value)  # pyright: ignore[reportArgumentType] -- runtime boundary validation


def test_count_rejects_booleans() -> None:
    for value in (True, False):
        with pytest.raises(TypeError, match="exact integer"):
            _ = Count(value=value)


def test_issue_defaults_to_error_severity() -> None:
    issue = Issue(code="invalid_definition", path=("definitions", 0), message="Invalid")

    assert issue.severity is IssueSeverity.ERROR


def test_issue_accepts_a_closed_severity_member() -> None:
    issue = Issue(
        code="missing_evidence",
        path=("evidence",),
        message="Evidence is missing",
        severity=IssueSeverity.WARNING,
    )

    assert issue.severity is IssueSeverity.WARNING


def test_issue_rejects_raw_enum_strings_at_runtime() -> None:
    with pytest.raises(TypeError, match="IssueSeverity"):
        _ = Issue(
            code="invalid_definition",
            path=(),
            message="Invalid",
            severity="error",  # pyright: ignore[reportArgumentType] -- runtime boundary validation
        )


def test_issue_snapshots_a_caller_owned_path() -> None:
    path: list[str | int] = ["definitions", 0]
    issue = Issue(
        code="invalid_definition",
        path=path,
        message="Invalid",
    )
    path.append("name")

    assert issue.path == ("definitions", 0)


def test_issue_rejects_a_string_as_a_path_sequence() -> None:
    with pytest.raises(TypeError, match="path"):
        _ = Issue(
            code="invalid_definition",
            path="definitions",
            message="Invalid",
        )


def test_issue_rejects_non_sequence_paths() -> None:
    with pytest.raises(TypeError, match="sequence"):
        _ = Issue(
            code="invalid_definition",
            path=42,  # pyright: ignore[reportArgumentType] -- runtime boundary validation
            message="Invalid",
        )


def test_issue_rejects_boolean_path_parts() -> None:
    with pytest.raises(TypeError, match="elements"):
        _ = Issue(code="invalid_definition", path=(True,), message="Invalid")


def test_page_snapshots_caller_owned_items_and_cursor_is_opaque() -> None:
    items = ["one", "two"]
    cursor = PageCursor("opaque-cursor")
    page = Page[str](items=items, next_cursor=cursor)
    items.append("three")

    assert page.items == ("one", "two")
    assert page.next_cursor == cursor


def test_page_rejects_a_string_as_an_item_sequence() -> None:
    with pytest.raises(TypeError, match="items"):
        _ = Page[str](items="one")


@pytest.mark.parametrize("buffer", [b"abc", bytearray(b"abc"), memoryview(b"abc")])
def test_records_reject_byte_buffers_as_collections(buffer: Sequence[int]) -> None:
    with pytest.raises(TypeError, match="Page items"):
        _ = Page[int](items=buffer)

    with pytest.raises(TypeError, match="Issue path"):
        _ = Issue(code="invalid_definition", path=buffer, message="Invalid")


def test_model_scope_requires_nominal_project_and_model_ids() -> None:
    scope = ModelScope(project_id=ProjectId("acme"), model_id=ModelId("catalog"))

    assert scope.project_id == ProjectId("acme")
    assert scope.model_id.value == "catalog"


def test_model_scope_rejects_a_review_case_id_as_its_model_id() -> None:
    with pytest.raises(TypeError, match="ModelId"):
        _ = ModelScope(
            project_id=ProjectId("acme"),
            model_id=ReviewCaseId("case-1"),  # pyright: ignore[reportArgumentType] -- runtime validation
        )


def test_model_version_and_pinned_definition_reference_are_exactly_scoped() -> None:
    scope = ModelScope(project_id=ProjectId("acme"), model_id=ModelId("catalog"))
    model = ModelVersion(
        scope=scope,
        version="1.0.0",
        content_hash=ContentHash(f"sha256:{'a' * 64}"),
    )
    reference = PinnedDefinitionReference(
        model=model,
        definition_id=DefinitionId("machine"),
        definition_revision=1,
    )

    assert reference.model is model
    assert reference.definition_id == DefinitionId("machine")
    assert reference.kind == "pinned_definition"


def test_model_version_rejects_an_empty_version_label() -> None:
    scope = ModelScope(project_id=ProjectId("acme"), model_id=ModelId("catalog"))

    with pytest.raises(ValueError, match="nonempty"):
        _ = ModelVersion(
            scope=scope,
            version="",
            content_hash=ContentHash(f"sha256:{'a' * 64}"),
        )


def test_definition_reference_union_keeps_company_and_pack_ids_nominal() -> None:
    company_reference: DefinitionReference = DefinitionId("machine")
    pack_reference: DefinitionReference = ReferenceDefinitionId("machine")

    assert type(company_reference) is DefinitionId
    assert type(pack_reference) is ReferenceDefinitionId
    assert company_reference != pack_reference


def test_pinned_definition_reference_rejects_an_unknown_discriminator() -> None:
    scope = ModelScope(project_id=ProjectId("acme"), model_id=ModelId("catalog"))
    model = ModelVersion(
        scope=scope,
        version="1.0.0",
        content_hash=ContentHash(f"sha256:{'a' * 64}"),
    )

    with pytest.raises(ValueError, match="pinned_definition"):
        _ = PinnedDefinitionReference(
            model=model,
            definition_id=DefinitionId("machine"),
            definition_revision=1,
            kind="other",  # pyright: ignore[reportArgumentType] -- runtime boundary validation
        )


def test_pinned_definition_reference_requires_positive_exact_revision() -> None:
    scope = ModelScope(project_id=ProjectId("acme"), model_id=ModelId("catalog"))
    model = ModelVersion(
        scope=scope,
        version="1.0.0",
        content_hash=ContentHash(f"sha256:{'a' * 64}"),
    )

    for revision in (0, -1):
        with pytest.raises(ValueError, match="positive"):
            _ = PinnedDefinitionReference(
                model=model,
                definition_id=DefinitionId("machine"),
                definition_revision=revision,
            )

    with pytest.raises(TypeError, match="exact integer"):
        _ = PinnedDefinitionReference(
            model=model,
            definition_id=DefinitionId("machine"),
            definition_revision=True,
        )


def test_issue_rejects_non_string_codes_and_empty_messages() -> None:
    with pytest.raises(ValueError, match="code"):
        _ = Issue(code="", path=(), message="Invalid")
    with pytest.raises(ValueError, match="message"):
        _ = Issue(code="invalid", path=(), message="")

    with pytest.raises(TypeError, match="code must be a string"):
        _ = Issue(code=17, path=(), message="Invalid")  # pyright: ignore[reportArgumentType] -- runtime validation

    with pytest.raises(TypeError, match="message must be a string"):
        _ = Issue(code="invalid", path=(), message=17)  # pyright: ignore[reportArgumentType] -- runtime validation


def test_contract_collection_inputs_are_sequences() -> None:
    path: Sequence[str | int] = ("definitions", 0)

    assert Issue(code="invalid", path=path, message="Invalid").path == path
