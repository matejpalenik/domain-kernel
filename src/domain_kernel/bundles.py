"""Portable public model releases and their structural integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from domain_kernel.modeling.domain.bundle_shapes import bundle_schema, parse_wire_record, wire_shape
from domain_kernel.modeling.domain.portable_json import PortableReadError, read_portable_object
from domain_kernel.modeling.domain.snapshot_integrity import release_digest, verify_bundle_integrity
from domain_kernel.modeling.domain.snapshots import DomainModelBundle
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.errors import (
    DomainKernelError,
    InvalidBundleError,
    UnsupportedBundleVersionError,
)
from domain_kernel.shared.hashing import canonical_json_bytes
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.hashing import JsonValue
    from domain_kernel.shared.identifiers.content_hash import ContentHash


__all__ = ["BundleValidation", "DomainModelBundle", "require_valid_bundle", "validate_bundle"]


@dataclass(frozen=True, kw_only=True)
class BundleValidation:
    """Structural and content integrity observations from the built-in codec."""

    valid: bool
    schema_version: str
    issues: Sequence[Issue]

    def __post_init__(self) -> None:
        """Detach callers' issue collections."""
        require_exact(value=self.valid, expected=bool, field="Bundle validation outcome")
        require_text(value=self.schema_version, field="Bundle schema version")
        object.__setattr__(
            self,
            "issues",
            snapshot_sequence(items=self.issues, item_type=Issue, field="Issues"),
        )


def _invalid(*, code: str, message: str) -> InvalidBundleError:
    return InvalidBundleError(issues=(Issue(code=code, path=(), message=message),))


def _wire_version(*, version: object) -> None:
    if type(version) is not str or version != "1.0":
        raise UnsupportedBundleVersionError


def _check_format(*, raw: dict[str, JsonValue]) -> None:
    if raw.get("format") != "domain-kernel.bundle":
        raise _invalid(code="bundle_format", message="Load a complete Domain Kernel bundle.")
    if type(raw.get("schema_version")) is not str:
        raise _invalid(code="bundle_format", message="Include the exact supported schema version.")
    _wire_version(version=raw["schema_version"])


@final
class _BundleCodec:
    """Bind exact format selection, closed field decoding and semantic integrity."""

    digest = staticmethod(release_digest)

    def deserialize(
        self,
        *,
        payload: bytes | str,
        expected_hash: ContentHash | None,
        max_bytes: int,
    ) -> DomainModelBundle:
        try:
            raw = read_portable_object(
                payload=payload,
                expected_hash=expected_hash,
                max_bytes=max_bytes,
                resource="bundle",
                max_depth=96,  # Accommodate up to 16 nested dependency publications.
            )
        except PortableReadError as error:
            raise InvalidBundleError(issues=(error.issue,)) from None
        _check_format(raw=raw)
        try:
            bundle = parse_wire_record(document=raw, record=DomainModelBundle)
        except (TypeError, ValueError, DomainKernelError, ArithmeticError, RecursionError):
            raise _invalid(
                code="bundle_shape",
                message="Use the exact declared bundle fields and types.",
            ) from None
        require_valid_bundle(bundle=bundle)
        return bundle

    def serialize(self, *, bundle: DomainModelBundle) -> bytes:
        require_valid_bundle(bundle=bundle)
        return canonical_json_bytes(value=wire_shape(hint=DomainModelBundle).render(bundle))

    def validate(self, *, bundle: DomainModelBundle) -> BundleValidation:
        require_exact(value=bundle, expected=DomainModelBundle, field="Bundle")
        _wire_version(version=bundle.schema_version)
        issues = list(verify_bundle_integrity(bundle=bundle))
        try:
            _ = canonical_json_bytes(value=wire_shape(hint=DomainModelBundle).render(bundle))
        except (TypeError, ValueError, ArithmeticError, RecursionError):
            issues.append(
                Issue(code="bundle_shape", path=(), message="Use the exact declared bundle fields.")
            )
        return BundleValidation(
            valid=all(issue.severity is not IssueSeverity.ERROR for issue in issues),
            schema_version=bundle.schema_version,
            issues=issues,
        )

    def schema(self, *, version: str) -> str:
        _wire_version(version=version)
        return canonical_json_bytes(value=bundle_schema(root=DomainModelBundle)).decode("utf-8")


PORTABLE_MODEL_CODEC = _BundleCodec()


def validate_bundle(*, bundle: DomainModelBundle) -> BundleValidation:
    """Check complete structural, reference and release integrity without I/O."""
    return PORTABLE_MODEL_CODEC.validate(bundle=bundle)


def require_valid_bundle(*, bundle: DomainModelBundle) -> None:
    """Require a trustworthy structural snapshot before using it in an operation."""
    result = validate_bundle(bundle=bundle)
    if not result.valid:
        raise InvalidBundleError(issues=result.issues)
