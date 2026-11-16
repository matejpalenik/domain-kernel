from __future__ import annotations

import pytest

from domain_kernel.modeling.domain.errors.model_not_found_error import ModelNotFoundError
from domain_kernel.projects.domain.errors.project_not_found_error import ProjectNotFoundError
from domain_kernel.publication.domain.errors.publication_blocked_error import (
    PublicationBlockedError,
)
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.errors import ConfigurationError, DomainKernelError, StaleStateError


def test_domain_kernel_error_exposes_message_code_and_retryability() -> None:
    error = DomainKernelError(
        message="Storage is unavailable",
        code="storage_unavailable",
        retryable=True,
    )

    assert str(error) == "Storage is unavailable"
    assert error.code == "storage_unavailable"
    assert error.retryable is True


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (ProjectNotFoundError(message="No project"), "project_not_found"),
        (ModelNotFoundError(message="No model"), "model_not_found"),
        (InvalidDecisionError(message="Invalid review action"), "invalid_decision"),
        (StaleStateError(message="State changed"), "stale_state"),
    ],
)
def test_typed_errors_have_stable_codes(error: DomainKernelError, expected_code: str) -> None:
    assert error.code == expected_code


def test_configuration_error_keeps_structured_issues_immutably() -> None:
    issues = [
        Issue(
            code="missing_path",
            path=("database", "path"),
            message="A database path is required",
            severity=IssueSeverity.ERROR,
        )
    ]
    error = ConfigurationError(issues=issues)
    issues.clear()

    assert error.code == "configuration_error"
    assert error.issues == (
        Issue(
            code="missing_path",
            path=("database", "path"),
            message="A database path is required",
            severity=IssueSeverity.ERROR,
        ),
    )


def test_publication_blocked_error_keeps_structured_issues() -> None:
    issue = Issue(
        code="unresolved_review",
        path=("review",),
        message="Review is incomplete",
    )
    error = PublicationBlockedError(issues=(issue,))

    assert error.code == "publication_blocked"
    assert error.issues == (issue,)


def test_domain_error_rejects_empty_code_and_message() -> None:
    with pytest.raises(ValueError, match="code"):
        _ = DomainKernelError(message="Failure", code="")
    with pytest.raises(ValueError, match="message"):
        _ = DomainKernelError(message="", code="failure")


def test_domain_error_rejects_wrong_types_and_non_boolean_retryability() -> None:
    with pytest.raises(TypeError, match="Error message"):
        _ = DomainKernelError(message=b"failure", code="failure")  # pyright: ignore[reportArgumentType] -- runtime validation
    with pytest.raises(TypeError, match="retryable"):
        _ = DomainKernelError(
            message="Failure",
            code="failure",
            retryable=1,  # pyright: ignore[reportArgumentType] -- runtime validation
        )


def test_configuration_error_requires_a_nonempty_issue_sequence() -> None:
    with pytest.raises(ValueError, match="at least one"):
        _ = ConfigurationError(issues=())

    with pytest.raises(TypeError, match="Issue values"):
        _ = ConfigurationError(issues=("bad issue",))  # pyright: ignore[reportArgumentType] -- runtime validation


def test_publication_blocked_error_requires_nonempty_issue_sequence() -> None:
    with pytest.raises(ValueError, match="at least one"):
        _ = PublicationBlockedError(issues=())

    with pytest.raises(TypeError, match="Issue values"):
        _ = PublicationBlockedError(issues=("bad issue",))  # pyright: ignore[reportArgumentType] -- runtime validation
