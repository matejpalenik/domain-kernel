"""Author, inspect and exchange immutable reference packs over the closed SDK format."""

from __future__ import annotations

from dataclasses import dataclass, replace
from re import fullmatch
from typing import TYPE_CHECKING, Literal

from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.modeling.domain.bundle_shapes import bundle_schema, parse_wire_record, wire_shape
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.modeling.domain.portable_json import PortableReadError, read_portable_object
from domain_kernel.reference_packs.domain.contracts import (
    ObligationKind,
    PackMaturity,
    Pattern,
    ReferenceAssetKind,
    ReferenceDefinition,
    ReferenceOrigin,
    ReferencePackComposition,
    ReferencePackDependency,
    ReferencePackImportManifest,
    ReferencePackObligation,
    ReferencePackValidation,
)
from domain_kernel.reference_packs.domain.identifiers.pattern_id import PatternId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.contracts import DefinitionReference, Issue
from domain_kernel.shared.domain.definitions import require_definition_selector
from domain_kernel.shared.domain.ontology_closure import OntologyClosure, materialized_terms
from domain_kernel.shared.domain.rdf import OntologyStatement
from domain_kernel.shared.domain.shape_graph import (
    adopted_ontologies,
    remap_shape,
    shape_ontology_terms,
    validate_body_graph,
)
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.errors import (
    DomainKernelError,
    InvalidReferencePackError,
    PatternNotFoundError,
    UnsupportedReferencePackVersionError,
)
from domain_kernel.shared.hashing import canonical_json_bytes, hash_json
from domain_kernel.shared.validation import (
    require_exact,
    require_text,
    snapshot_sequence,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.hashing import JsonValue
    from domain_kernel.shared.identifiers.content_hash import ContentHash

_MAPPING_VERSION = "1.0"
_SUPPORTED_SEMANTICS = frozenset({"domain-kernel.core@1.0"})
_PACK_FORMAT: Literal["domain-kernel.reference-pack"] = "domain-kernel.reference-pack"


def _issue(*, code: str, message: str, path: tuple[str, ...] = ()) -> Issue:
    return Issue(code=code, message=message, path=path)


def _findings(
    *,
    issues: Sequence[Issue],
    obligations: Sequence[ReferencePackObligation],
) -> ReferencePackValidation:
    return ReferencePackValidation(
        valid=all(issue.severity is not IssueSeverity.ERROR for issue in issues),
        issues=issues,
        required_capabilities=tuple(
            dict.fromkeys(item.validator_id for item in obligations if item.required)
        ),
    )


@dataclass(frozen=True, kw_only=True)
class ReferencePackSpec:
    """Declare local materials and explicitly selected immutable pack imports."""

    key: str
    version: str
    title: str
    applicability: str
    provenance: str
    license: str
    exclusions: Sequence[str] = ()
    maturity: PackMaturity = PackMaturity.EXPERIMENTAL
    semantic_mapping_version: str = _MAPPING_VERSION
    supported_semantics: Sequence[str] = ()
    imports: Sequence[ReferencePackImport] = ()
    definitions: Sequence[ReferenceDefinition] = ()
    patterns: Sequence[Pattern] = ()
    obligations: Sequence[ReferencePackObligation] = ()
    dependencies: Sequence[ReferencePackDependency] = ()
    ontology_statements: Sequence[OntologyStatement] = ()
    ontologies: Sequence[OntologyClosure] = ()

    def __post_init__(self) -> None:
        """Freeze explicitly authored inputs before composing the immutable result."""
        require_text(value=self.key, field="Pack key")
        require_text(value=self.version, field="Pack version")
        _freeze_inputs(pack=self)
        object.__setattr__(
            self,
            "imports",
            snapshot_sequence(
                items=self.imports,
                item_type=ReferencePackImport,
                field="Explicit imports",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ReferencePack:
    """Portable, attributed reference assets and their exact selection history."""

    pin: ReferencePackPin
    title: str
    applicability: str
    exclusions: Sequence[str]
    maturity: PackMaturity
    provenance: str
    license: str
    definitions: Sequence[ReferenceDefinition]
    dependencies: Sequence[ReferencePackDependency]
    obligations: Sequence[ReferencePackObligation]
    supported_semantics: Sequence[str]
    semantic_mapping_version: str
    patterns: Sequence[Pattern] = ()
    ontology_statements: Sequence[OntologyStatement] = ()
    ontologies: Sequence[OntologyClosure] = ()
    composition: ReferencePackComposition | None = None
    schema_version: Literal["1.0"] = "1.0"
    format: Literal["domain-kernel.reference-pack"] = _PACK_FORMAT

    def __post_init__(self) -> None:
        """Detach accessible records and associate their containing pack pin."""
        require_exact(value=self.pin, expected=ReferencePackPin, field="Pack pin")
        _wire_version(version=self.schema_version)
        require_exact(value=self.format, expected=str, field="Pack format")
        if self.format != _PACK_FORMAT:
            raise ValueError("Use the exact reference-pack format")
        if self.composition is not None:
            require_exact(
                value=self.composition, expected=ReferencePackComposition, field="Composition"
            )
        _freeze_inputs(pack=self)
        object.__setattr__(
            self, "definitions", tuple(item.associate(pin=self.pin) for item in self.definitions)
        )
        object.__setattr__(
            self, "patterns", tuple(item.associate(pin=self.pin) for item in self.patterns)
        )

    @classmethod
    def compose(cls, *, spec: ReferencePackSpec, actor: str, reason: str) -> ReferencePackBuild:
        """Materialize explicit imports and return their structural diagnostics."""
        require_exact(value=spec, expected=ReferencePackSpec, field="Pack composition spec")
        require_text(value=actor, field="Composition actor")
        require_text(value=reason, field="Composition reason")
        return _compose(spec=spec, actor=actor, reason=reason)

    def validate(self) -> ReferencePackValidation:
        """Check exact graph, selection, dependency and content integrity."""
        issues = list(_structure_issues(pack=self))
        if _pack_digest(pack=self) != self.pin.content_hash:
            issues.append(
                _issue(code="reference_pack_hash", message="Retrieve the exact pack content.")
            )
        return _findings(issues=issues, obligations=self.obligations)

    def serialize(self) -> bytes:
        """Return canonical UTF-8 JSON that preserves the full authored pack."""
        _require_pack(pack=self)
        return canonical_json_bytes(value=wire_shape(hint=ReferencePack).render(self))

    @classmethod
    def deserialize(
        cls,
        *,
        payload: bytes | str,
        expected_hash: ContentHash | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> ReferencePack:
        """Load exact bounded bytes, verify the closed format and associate the pin."""
        try:
            raw = read_portable_object(
                payload=payload,
                expected_hash=expected_hash,
                max_bytes=max_bytes,
                resource="reference_pack",
            )
        except PortableReadError as error:
            raise InvalidReferencePackError(issues=(error.issue,)) from None
        _check_pack_format(document=raw)
        try:
            result = parse_wire_record(document=raw, record=ReferencePack)
        except (ValueError, TypeError, DomainKernelError, ArithmeticError, RecursionError):
            raise InvalidReferencePackError(
                issues=(
                    _issue(
                        code="reference_pack_shape",
                        message="Supply the exact declared reference-pack fields.",
                    ),
                )
            ) from None
        _require_pack(pack=result)
        return result

    @classmethod
    def get_json_schema(cls, *, schema_version: str = "1.0") -> str:
        """Return the complete closed JSON Schema for this exact wire version."""
        _wire_version(version=schema_version)
        return canonical_json_bytes(value=bundle_schema(root=ReferencePack)).decode("utf-8")

    def get_pattern(
        self, *, name: str | None = None, pattern_id: PatternId | None = None
    ) -> Pattern:
        """Read one authored pattern in this exact materialized pack."""
        require_definition_selector(name=name, item_id=pattern_id, id_type=PatternId)
        for pattern in self.patterns:
            if pattern.name == name or pattern.id == pattern_id:
                return pattern
        raise PatternNotFoundError


def _require_pack(*, pack: ReferencePack) -> None:
    validation = pack.validate()
    if not validation.valid:
        raise InvalidReferencePackError(issues=validation.issues)


@dataclass(frozen=True, kw_only=True)
class ReferencePackImport:
    """Select patterns and obligations from one supplied exact upstream pack."""

    reference_pack: ReferencePack
    namespace: str
    obligation_ids: Sequence[ObligationId]
    pattern_ids: Sequence[PatternId] = ()

    def __post_init__(self) -> None:
        """Retain selections so composition can report all invalid choices."""
        require_exact(value=self.reference_pack, expected=ReferencePack, field="Imported pack")
        require_text(value=self.namespace, field="Import namespace")
        object.__setattr__(
            self,
            "obligation_ids",
            snapshot_sequence(
                items=self.obligation_ids,
                item_type=ObligationId,
                field="Imported obligations",
            ),
        )
        object.__setattr__(
            self,
            "pattern_ids",
            snapshot_sequence(
                items=self.pattern_ids,
                item_type=PatternId,
                field="Imported patterns",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ReferencePackBuild:
    """A complete result, with no usable pack when composition has errors."""

    pack: ReferencePack | None
    validation: ReferencePackValidation


def _freeze_inputs(*, pack: ReferencePack | ReferencePackSpec) -> None:
    for field, value in (
        ("Title", pack.title),
        ("Applicability", pack.applicability),
        ("Provenance", pack.provenance),
        ("License", pack.license),
        ("Mapping version", pack.semantic_mapping_version),
    ):
        require_text(value=value, field=field)
    require_exact(value=pack.maturity, expected=PackMaturity, field="Pack maturity")
    for field, items, expected in (
        ("definitions", pack.definitions, ReferenceDefinition),
        ("patterns", pack.patterns, Pattern),
        ("obligations", pack.obligations, ReferencePackObligation),
        ("dependencies", pack.dependencies, ReferencePackDependency),
        ("exclusions", pack.exclusions, str),
        ("supported_semantics", pack.supported_semantics, str),
        ("ontology_statements", pack.ontology_statements, OntologyStatement),
        ("ontologies", pack.ontologies, OntologyClosure),
    ):
        object.__setattr__(
            pack, field, snapshot_sequence(items=items, item_type=expected, field=field)
        )


def _wire_version(*, version: str) -> None:
    if type(version) is not str or version != "1.0":
        raise UnsupportedReferencePackVersionError


def _check_pack_format(*, document: dict[str, JsonValue]) -> None:
    version = document.get("schema_version")
    if document.get("format") != _PACK_FORMAT or type(version) is not str:
        raise InvalidReferencePackError(
            issues=(
                _issue(
                    code="reference_pack_format",
                    message="Supply a complete versioned reference pack.",
                ),
            )
        )
    _wire_version(version=version)


def _pack_digest(*, pack: ReferencePack) -> ContentHash:
    wire = wire_shape(hint=ReferencePack).render(pack)
    if not isinstance(wire, dict) or not isinstance(pin := wire["pin"], dict):
        raise TypeError("Use the registered reference-pack representation")
    del pin["content_hash"]
    return hash_json(value=wire)


def _structure_issues(*, pack: ReferencePack) -> tuple[Issue, ...]:
    issues: list[Issue] = []
    if (
        pack.semantic_mapping_version != _MAPPING_VERSION
        or set(pack.supported_semantics) - _SUPPORTED_SEMANTICS
    ):
        issues.append(
            _issue(
                code="unsupported_semantics",
                message="Select registered pack mapping capabilities.",
            )
        )
    issues.extend(_graph_issues(pack=pack))
    issues.extend(_ontology_issues(pack=pack))
    issues.extend(_dependency_issues(pack=pack))
    if pack.composition is not None:
        issues.extend(_manifest_issues(pack=pack, manifests=pack.composition.imports))
    return tuple(issues)


def _ontology_issues(*, pack: ReferencePack) -> tuple[Issue, ...]:
    definitions = (
        *pack.definitions,
        *(entry for item in pack.patterns for entry in item.definitions),
    )
    modules = adopted_ontologies(bodies=(item.body for item in definitions))
    verified_terms = materialized_terms(closures=(*pack.ontologies, *modules))
    return tuple(
        _issue(
            code="ontology_term_missing",
            message="Supply the source closure containing this exact term and declared kind.",
            path=("definitions", definition.id.value, "ontology_terms", term.term_iri.value),
        )
        for definition in definitions
        for term in (*definition.ontology_terms, *shape_ontology_terms(body=definition.body))
        if term not in verified_terms
    )


def _graph_issues(*, pack: ReferencePack) -> list[Issue]:
    issues: list[Issue] = []
    by_id = {item.id: item for item in pack.definitions}
    if len(by_id) != len(pack.definitions):
        issues.append(
            _issue(code="duplicate_definition", message="Use a distinct ID per pack definition.")
        )
    if len({item.id for item in pack.patterns}) != len(pack.patterns):
        issues.append(
            _issue(code="duplicate_pattern", message="Use a distinct ID per pack pattern.")
        )
    if len({item.name for item in pack.patterns}) != len(pack.patterns):
        issues.append(
            _issue(
                code="duplicate_pattern_name",
                message="Choose distinct names for imported patterns.",
            )
        )
    if len({item.id for item in pack.obligations}) != len(pack.obligations):
        issues.append(
            _issue(code="duplicate_obligation", message="Use a distinct ID per pack obligation.")
        )
    discovered = by_id.copy()
    for pattern in pack.patterns:
        issues.extend(_pattern_issues(pattern=pattern, packaged=discovered))
        discovered.update({member.id: member for member in pattern.definitions})
    issues.extend(
        validate_body_graph(
            bodies={identifier: item.body for identifier, item in by_id.items()},
            ontologies=pack.ontologies,
        )
    )
    issues.extend(
        _issue(
            code="obligation_reference",
            message="Select definitions materialized in the pack.",
            path=("obligations", obligation.id.value),
        )
        for obligation in pack.obligations
        if not set(obligation.reference_ids) <= by_id.keys()
    )
    return issues


def _pattern_issues(
    *,
    pattern: Pattern,
    packaged: dict[ReferenceDefinitionId, ReferenceDefinition],
) -> tuple[Issue, ...]:
    by_id = {item.id: item for item in pattern.definitions}
    if (
        len(by_id) != len(pattern.definitions)
        or not pattern.entrypoint_ids
        or len(set(pattern.entrypoint_ids)) != len(pattern.entrypoint_ids)
        or not set(pattern.entrypoint_ids) <= by_id.keys()
    ):
        return (
            _issue(
                code="pattern_entrypoints",
                path=("patterns", pattern.name),
                message="Supply distinct pattern members and exact local entrypoints.",
            ),
        )
    conflicting = tuple(
        _issue(
            code="pattern_definition_conflict",
            path=("patterns", pattern.name, member.id.value),
            message="Retain the same exact definition in the pack and its pattern.",
        )
        for member in pattern.definitions
        if member.id in packaged and packaged[member.id] != member
    )
    return (
        *conflicting,
        *validate_body_graph(
            bodies={item.id: item.body for item in pattern.definitions},
        ),
    )


def _dependency_issues(*, pack: ReferencePack) -> tuple[Issue, ...]:
    assets: dict[str, ReferencePackDependency] = {}
    issues: list[Issue] = []
    for dependency in pack.dependencies:
        if dependency.key == pack.pin.key or dependency.key in assets:
            issues.append(
                _issue(
                    code="dependency_conflict",
                    path=("dependencies", dependency.key),
                    message="Select one exact nonrecursive dependency per key.",
                )
            )
        else:
            assets[dependency.key] = dependency
    return tuple(issues)


def _manifest_issues(
    *,
    pack: ReferencePack,
    manifests: Sequence[ReferencePackImportManifest],
) -> tuple[Issue, ...]:
    issues: list[Issue] = []
    namespaces: set[str] = set()
    dependencies = {
        (item.key, item.version, item.content_hash)
        for item in pack.dependencies
        if item.kind is ReferenceAssetKind.REFERENCE_PACK
    }
    for manifest in manifests:
        namespace = manifest.namespace
        pin = manifest.reference_pack
        if namespace in namespaces or not _valid_namespace(namespace=namespace):
            issues.append(_issue(code="import_namespace", message="Use distinct valid namespaces."))
        namespaces.add(namespace)
        if (pin.key, pin.version, pin.content_hash) not in dependencies:
            issues.append(
                _issue(code="import_dependency", message="Preserve the exact imported pack pin.")
            )
        issues.extend(_selection_issues(pack=pack, manifest=manifest))
        issues.extend(_omission_warnings(manifest=manifest))
    return tuple(issues)


def _selection_issues(
    *, pack: ReferencePack, manifest: ReferencePackImportManifest
) -> tuple[Issue, ...]:
    namespace = manifest.namespace
    selected_patterns = {f"{namespace}:{item.value}" for item in manifest.pattern_ids}
    selected_obligations = {f"{namespace}:{item.value}" for item in manifest.obligation_ids}
    omitted = {item.id for item in manifest.omitted_obligations}
    if (
        len(selected_patterns) != len(manifest.pattern_ids)
        or len(selected_obligations) != len(manifest.obligation_ids)
        or len(omitted) != len(manifest.omitted_obligations)
        or omitted.intersection(manifest.obligation_ids)
        or not selected_patterns <= {item.id.value for item in pack.patterns}
        or not selected_obligations <= {item.id.value for item in pack.obligations}
    ):
        return (
            _issue(
                code="invalid_import_selection",
                message="Preserve exact selected and omitted members.",
                path=("composition", namespace),
            ),
        )
    return ()


def _omission_warnings(*, manifest: ReferencePackImportManifest) -> tuple[Issue, ...]:
    return tuple(
        Issue(
            code="omitted_required_obligation",
            message="This required upstream obligation was deliberately omitted.",
            path=("composition", manifest.namespace, item.id.value),
            severity=IssueSeverity.WARNING,
        )
        for item in manifest.omitted_obligations
        if item.required
    )


def _valid_namespace(*, namespace: str) -> bool:
    return fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", namespace) is not None


@dataclass(frozen=True, kw_only=True)
class _ImportedRecords:
    manifest: ReferencePackImportManifest
    definitions: tuple[ReferenceDefinition, ...]
    patterns: tuple[Pattern, ...]
    obligations: tuple[ReferencePackObligation, ...]
    dependencies: tuple[ReferencePackDependency, ...]


def _selection_problems(*, imported: ReferencePackImport) -> tuple[Issue, ...]:
    pack = imported.reference_pack
    issues = list(pack.validate().issues)
    if (
        len(set(imported.pattern_ids)) != len(imported.pattern_ids)
        or not set(imported.pattern_ids) <= {item.id for item in pack.patterns}
        or len(set(imported.obligation_ids)) != len(imported.obligation_ids)
        or not set(imported.obligation_ids) <= {item.id for item in pack.obligations}
    ):
        issues.append(
            _issue(
                code="invalid_import_selection",
                path=("imports", imported.namespace),
                message="Select exact patterns and obligations from the imported pack.",
            )
        )
    if any(
        item.id in imported.obligation_ids
        and item.required
        and item.kind is ObligationKind.SEMANTIC
        for item in pack.obligations
    ):
        issues.append(
            _issue(
                code="unsupported_remapping",
                path=("imports", imported.namespace),
                message="Required semantic obligations need a registered remapper.",
            )
        )
    return tuple(issues)


def _clone_import(*, imported: ReferencePackImport) -> _ImportedRecords:
    source = imported.reference_pack
    prefix = f"{imported.namespace}:"
    selected = [pattern for pattern in source.patterns if pattern.id in imported.pattern_ids]
    all_members = (
        *source.definitions,
        *(item for pattern in selected for item in pattern.definitions),
    )
    reference_ids = {
        item.id: ReferenceDefinitionId(value=prefix + item.id.value) for item in all_members
    }
    replacements = dict[DefinitionReference, DefinitionReference](reference_ids.items())

    def clone(item: ReferenceDefinition) -> ReferenceDefinition:
        origin = ReferenceOrigin(reference_pack=source.pin, definition_id=item.id)
        return replace(
            item,
            id=reference_ids[item.id],
            body=remap_shape(body=item.body, replacements=replacements),
            origins=(origin, *item.origins),
        )

    return _ImportedRecords(
        manifest=ReferencePackImportManifest(
            reference_pack=source.pin,
            namespace=imported.namespace,
            pattern_ids=imported.pattern_ids,
            obligation_ids=imported.obligation_ids,
            omitted_obligations=tuple(
                item for item in source.obligations if item.id not in imported.obligation_ids
            ),
        ),
        definitions=tuple(clone(item) for item in source.definitions),
        patterns=tuple(
            Pattern.restore(
                id=PatternId(value=prefix + item.id.value),
                name=item.name,
                display_name=item.display_name,
                description=item.description,
                definitions=tuple(clone(entry) for entry in item.definitions),
                entrypoint_ids=tuple(reference_ids[entry] for entry in item.entrypoint_ids),
            )
            for item in selected
        ),
        obligations=tuple(
            replace(
                item,
                id=ObligationId(value=prefix + item.id.value),
                reference_ids=tuple(reference_ids[ref] for ref in item.reference_ids),
            )
            for item in source.obligations
            if item.id in imported.obligation_ids
        ),
        dependencies=(
            *source.dependencies,
            ReferencePackDependency(
                key=source.pin.key,
                version=source.pin.version,
                content_hash=source.pin.content_hash,
                kind=ReferenceAssetKind.REFERENCE_PACK,
                provenance=source.provenance,
                license=source.license,
            ),
        ),
    )


def _compose(*, spec: ReferencePackSpec, actor: str, reason: str) -> ReferencePackBuild:
    issues: list[Issue] = []
    namespaces = {item.namespace for item in spec.imports}
    if len(namespaces) != len(spec.imports) or any(
        not _valid_namespace(namespace=item) for item in namespaces
    ):
        issues.append(_issue(code="import_namespace", message="Use distinct valid namespaces."))
    for imported in spec.imports:
        issues.extend(_selection_problems(imported=imported))
    if any(issue.severity is IssueSeverity.ERROR for issue in issues):
        return ReferencePackBuild(pack=None, validation=_findings(issues=issues, obligations=()))
    records = tuple(_clone_import(imported=imported) for imported in spec.imports)
    draft = _materialize(spec=spec, records=records, actor=actor, reason=reason)
    pack = replace(draft, pin=replace(draft.pin, content_hash=_pack_digest(pack=draft)))
    validation = pack.validate()
    return ReferencePackBuild(pack=pack if validation.valid else None, validation=validation)


def _materialize(
    *,
    spec: ReferencePackSpec,
    records: Sequence[_ImportedRecords],
    actor: str,
    reason: str,
) -> ReferencePack:
    dependencies = tuple(
        dict.fromkeys(
            (
                *spec.dependencies,
                *(item for row in records for item in row.dependencies),
            )
        )
    )
    semantics = tuple(
        dict.fromkeys(
            (
                *spec.supported_semantics,
                *(
                    name
                    for choice in spec.imports
                    for name in choice.reference_pack.supported_semantics
                ),
            )
        )
    )
    return ReferencePack(
        pin=ReferencePackPin(
            key=spec.key, version=spec.version, content_hash=hash_json(value=None)
        ),
        title=spec.title,
        applicability=spec.applicability,
        exclusions=spec.exclusions,
        maturity=spec.maturity,
        provenance=spec.provenance,
        license=spec.license,
        definitions=(*spec.definitions, *(item for row in records for item in row.definitions)),
        dependencies=dependencies,
        obligations=(*spec.obligations, *(item for row in records for item in row.obligations)),
        patterns=(*spec.patterns, *(item for row in records for item in row.patterns)),
        supported_semantics=semantics,
        ontologies=tuple(
            dict.fromkeys(
                (
                    *spec.ontologies,
                    *(
                        closure
                        for choice in spec.imports
                        for closure in choice.reference_pack.ontologies
                    ),
                )
            )
        ),
        ontology_statements=tuple(
            dict.fromkeys(
                (
                    *spec.ontology_statements,
                    *(
                        statement
                        for choice in spec.imports
                        for statement in choice.reference_pack.ontology_statements
                    ),
                )
            )
        ),
        semantic_mapping_version=spec.semantic_mapping_version,
        composition=ReferencePackComposition(
            imports=tuple(row.manifest for row in records),
            actor=actor,
            reason=reason,
        ),
    )
