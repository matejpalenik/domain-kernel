"""Compile authored SHACL Core shapes against explicit mapped graph roles."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING
from urllib.parse import quote

from domain_kernel._shared.domain.artifacts import SemanticGraphRole
from domain_kernel._shared.domain.business_decisions import RuleDefinition
from domain_kernel._shared.domain.data_shapes import ConstraintLanguage, ConstraintTarget
from domain_kernel._shared.domain.ontology_assets import (
    BlankNode,
    Iri,
    OntologyDocumentPin,
    OntologySyntax,
)
from domain_kernel._shared.domain.ontology_documents import OntologyDocument, OntologyLimits
from domain_kernel._shared.domain.ontology_errors import InvalidOntologyError
from domain_kernel._shared.domain.rdf import OntologyStatement, RdfLiteral
from domain_kernel.modeling.domain.rdf_graphs import DK, RDF, SH, XSD
from domain_kernel.ontologies import load_ontology
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import ResourceLimitError
from domain_kernel.shared.hashing import hash_bytes, hash_json

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.data_shapes import ConstraintDefinition
    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel.modeling.domain.rdf_graphs import RdfModelGraphs


# Registered declarative subset. Executable constraints and fetchable imports
# are outside this vocabulary. Pattern matching is intentionally absent.
SHACL_CORE_PREDICATES = frozenset(
    f"{SH}{name}"
    for name in (
        "targetClass",
        "targetNode",
        "property",
        "path",
        "node",
        "class",
        "datatype",
        "nodeKind",
        "minCount",
        "maxCount",
        "hasValue",
        "in",
        "minLength",
        "maxLength",
        "minInclusive",
        "maxInclusive",
        "minExclusive",
        "maxExclusive",
        "closed",
    )
)
_LIST = frozenset(f"{RDF}{name}" for name in ("first", "rest"))
CONTROLLED_SHAPE_PREDICATES = (
    SHACL_CORE_PREDICATES
    | _LIST
    | {
        f"{RDF}type",
        f"{SH}inversePath",
        f"{SH}or",
        f"{SH}not",
    }
)
_LINKS = frozenset(f"{SH}{name}" for name in ("node", "property", "in"))
_META_CLASSES = frozenset({Iri(value=f"{DK}DefinitionRevision"), Iri(value=f"{DK}ValueSet")})
_KIND = frozenset(
    Iri(value=f"{SH}{name}")
    for name in (
        "IRI",
        "BlankNode",
        "Literal",
        "BlankNodeOrIRI",
        "IRIOrLiteral",
        "BlankNodeOrLiteral",
    )
)
_SHAPE_TYPE = frozenset({Iri(value=f"{SH}NodeShape"), Iri(value=f"{SH}PropertyShape")})
_MAX_BYTES = 512 * 1024
_MAX_STATEMENTS = 1_000
_MAX_CONSTRAINTS = 64


@dataclass(frozen=True, kw_only=True)
class AuthoredShapes:
    """Checked authored shapes and paths kept distinct by their intended target."""

    model: tuple[OntologyStatement, ...]
    instance: tuple[OntologyStatement, ...]
    locations: tuple[tuple[Iri, tuple[str | int, ...]], ...]
    issues: tuple[Issue, ...]


@dataclass(frozen=True, kw_only=True)
class _Targets:
    paths: frozenset[Iri]
    classes: frozenset[Iri]
    nodes: frozenset[Iri]
    generated: frozenset[Iri]


def _targets(*, graphs: RdfModelGraphs, target: ConstraintTarget) -> _Targets:
    by_role = dict(graphs.documents)
    if target is ConstraintTarget.MODEL:
        data = by_role[SemanticGraphRole.MODEL_METADATA]
        return _Targets(
            paths=frozenset(
                (
                    *(row.predicate for row in data),
                    Iri(value=f"{DK}alias"),
                    Iri(value=f"{DK}displayName"),
                    Iri(value=f"{DK}meaning"),
                )
            ),
            classes=_META_CLASSES,
            nodes=frozenset(row.subject for row in data if isinstance(row.subject, Iri)),
            generated=frozenset(
                row.subject
                for row in by_role[SemanticGraphRole.MODEL_SHAPES]
                if isinstance(row.subject, Iri)
            ),
        )
    shapes = by_role[SemanticGraphRole.INSTANCE_SHAPES]
    return _Targets(
        paths=frozenset(
            row.object
            for row in shapes
            if row.predicate.value in (f"{SH}path", f"{SH}inversePath")
            and isinstance(row.object, Iri)
        ),
        classes=frozenset(
            row.object
            for row in shapes
            if row.predicate.value == f"{SH}targetClass" and isinstance(row.object, Iri)
        ),
        nodes=frozenset(),
        generated=frozenset(row.subject for row in shapes if isinstance(row.subject, Iri)),
    )


def _allowed(  # noqa: C901, PLR0911 - Explicitly validate every admitted SHACL predicate.
    *,
    statement: OntologyStatement,
    targets: _Targets,
    subjects: set[Iri | BlankNode],
) -> bool:
    pred = statement.predicate.value
    value = statement.object
    if pred == f"{RDF}type":
        return value in _SHAPE_TYPE
    if pred in _LIST:
        return pred == f"{RDF}first" or value in subjects or value == Iri(value=f"{RDF}nil")
    if pred not in SHACL_CORE_PREDICATES:
        return False
    if pred in _LINKS:
        return (
            value in subjects
            or value in targets.generated
            or (pred == f"{SH}in" and value == Iri(value=f"{RDF}nil"))
        )
    if pred == f"{SH}targetNode":
        return value in targets.nodes
    if pred in (f"{SH}targetClass", f"{SH}class"):
        return value in targets.classes
    if pred == f"{SH}path":
        return value in targets.paths
    if pred == f"{SH}datatype":
        return isinstance(value, Iri) and value.value.startswith(XSD)
    if pred == f"{SH}nodeKind":
        return value in _KIND
    if pred == f"{SH}hasValue":
        return isinstance(value, (RdfLiteral, Iri))
    return isinstance(value, RdfLiteral)


def _isolated_shapes(
    *,
    assertions: Sequence[OntologyStatement],
    base: Iri,
    owner: Definition,
    constraint: ConstraintDefinition,
    targets: _Targets,
) -> tuple[OntologyStatement, ...]:
    subjects = {row.subject for row in assertions}
    if not assertions or not any(
        row.predicate.value in (f"{SH}targetClass", f"{SH}targetNode") for row in assertions
    ):
        raise InvalidOntologyError(message="Declare at least one explicit valid shape target.")
    if not all(_allowed(statement=row, targets=targets, subjects=subjects) for row in assertions):
        raise InvalidOntologyError(
            message="Use the registered SHACL subset and scoped mapped targets."
        )
    identity = quote(owner.id.value, safe="")
    label = quote(constraint.id, safe="")
    names = {
        item: Iri(
            value=f"{base.value}constraints/{identity}/{label}/"
            + hash_json(
                value=(item.kind, item.value if isinstance(item, Iri) else item.id),
            ).value.removeprefix("sha256:")
        )
        for item in subjects
    }
    return tuple(
        OntologyStatement(
            subject=names[row.subject],
            predicate=row.predicate,
            object=names.get(row.object, row.object)
            if row.predicate.value in (*_LINKS, f"{RDF}rest")
            and isinstance(row.object, (Iri, BlankNode))
            else row.object,
        )
        for row in assertions
    )


def compile_shacl(
    *,
    definitions: Sequence[Definition],
    base: Iri,
    graphs: RdfModelGraphs,
) -> AuthoredShapes:
    """Resolve only scoped mapped targets and capture the declared graph roles."""
    model: list[OntologyStatement] = []
    instance: list[OntologyStatement] = []
    issues: list[Issue] = []
    locations: list[tuple[Iri, tuple[str | int, ...]]] = []
    selections: list[tuple[Definition, ConstraintDefinition, int]] = []
    for definition in definitions:
        if isinstance(definition.body, RuleDefinition):
            selections.extend(
                (definition, constraint, offset)
                for offset, constraint in enumerate(definition.body.constraints)
                if constraint.language is ConstraintLanguage.SHACL
            )
    if len(selections) > _MAX_CONSTRAINTS:
        issue = Issue(
            code="shacl_resource_limit",
            path=("definitions",),
            message="Use fewer authored SHACL shapes.",
        )
        return AuthoredShapes(model=(), instance=(), locations=(), issues=(issue,))
    deadline = monotonic() + 30
    for owner, constraint, offset in selections:
        path = ("definitions", owner.id.value, "constraints", offset)
        payload = constraint.expression.encode("utf-8")
        if len(payload) > _MAX_BYTES or monotonic() >= deadline:
            issues.append(
                Issue(
                    code="shacl_resource_limit",
                    path=path,
                    message="Use a smaller authored SHACL graph.",
                )
            )
            continue
        try:
            document = OntologyDocument(
                pin=OntologyDocumentPin(
                    document_iri=base, content_hash=hash_bytes(content=payload)
                ),
                syntax=OntologySyntax.TURTLE,
                payload=payload,
            )
            parsed = load_ontology(
                document=document,
                limits=OntologyLimits(
                    max_bytes=_MAX_BYTES,
                    max_statements=_MAX_STATEMENTS,
                    timeout_ms=max(1, int((deadline - monotonic()) * 1000)),
                ),
            )
            assertions = _isolated_shapes(
                assertions=parsed.documents[0].statements,
                base=base,
                owner=owner,
                constraint=constraint,
                targets=_targets(graphs=graphs, target=constraint.target),
            )
        except InvalidOntologyError:
            issues.append(
                Issue(
                    code="unsupported_shacl_shape",
                    path=path,
                    message="Use supported Core predicates and mapped targets for this role.",
                )
            )
        except ResourceLimitError:
            issues.append(
                Issue(
                    code="shacl_resource_limit",
                    path=path,
                    message="Use a smaller authored SHACL graph.",
                )
            )
        else:
            selected = model if constraint.target is ConstraintTarget.MODEL else instance
            selected.extend(assertions)
            locations.extend(
                (row.subject, path) for row in assertions if isinstance(row.subject, Iri)
            )
    return AuthoredShapes(
        model=tuple(model),
        instance=tuple(instance),
        locations=tuple(dict.fromkeys(locations)),
        issues=tuple(issues),
    )
