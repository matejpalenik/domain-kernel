"""Opt-in ROBOT/HermiT host adapter for explicitly scoped named-class reasoning."""

from __future__ import annotations

import asyncio
import os
from hashlib import file_digest
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, final

from domain_kernel import (
    Iri,
    OntologyCapabilities,
    OntologyClosure,
    OntologyDocument,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologyStatement,
    OntologySyntax,
    ReasoningProfile,
    ReasoningResult,
    ReasoningSupport,
    ReasoningTask,
    ResourceLimitError,
    SemanticRegime,
    SemanticStatus,
    UnsupportedCapabilityError,
    load_ontology,
)
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel import OntologyLimits, ReasoningRequest

ROBOT_ENV = "DOMAIN_KERNEL_TOUR_ROBOT_JAR"
ROBOT_SHA256 = "53cd275c8e4c0dad1fc2c1c34174876795cd7d6b6926e1444adcbb0cb3c7ab26"
_ROBOT_SIZE = 82_708_624
_DRIVER = Path(__file__).with_name("RobotOntology.java")
_OWL = "http://www.w3.org/2002/07/owl#"
_TYPE = Iri(value="http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
_SUBCLASS = Iri(value="http://www.w3.org/2000/01/rdf-schema#subClassOf")
_DECLARATIONS = {
    Iri(value=f"{_OWL}Class"): "class",
    Iri(value="http://www.w3.org/2000/01/rdf-schema#Class"): "class",
    Iri(value=f"{_OWL}NamedIndividual"): "individual",
}
_OPERATIONS = {
    _SUBCLASS: "sub",
    Iri(value=f"{_OWL}equivalentClass"): "equivalent",
    Iri(value=f"{_OWL}disjointWith"): "disjoint",
}
_ONTOLOGY = Iri(value=f"{_OWL}Ontology")
_HEADER_PREDICATES = frozenset(Iri(value=f"{_OWL}{name}") for name in ("versionIRI", "imports"))
_BUILTIN_CLASSES = {Iri(value=f"{_OWL}{name}") for name in ("Thing", "Nothing")}


def named_class_scope(
    *, identity: Iri, specializations: Sequence[tuple[Iri, Iri]]
) -> OntologyClosure:
    """Materialize a deliberately authored scope of identified subclass assertions."""
    classes = {term for pair in specializations for term in pair}
    rows = [
        f"<{identity.value}> <{_TYPE.value}> <{_ONTOLOGY.value}> .",
        *(f"<{term.value}> <{_TYPE.value}> <{_OWL}Class> ." for term in classes),
        *(
            f"<{child.value}> <{_SUBCLASS.value}> <{parent.value}> ."
            for child, parent in specializations
        ),
    ]
    payload = ("\n".join(sorted(rows)) + "\n").encode()
    return load_ontology(
        document=OntologyDocument(
            pin=OntologyDocumentPin(
                document_iri=identity,
                ontology_iri=identity,
                content_hash=Hashing.hash_bytes(content=payload),
            ),
            syntax=OntologySyntax.NTRIPLES,
            payload=payload,
        )
    )


def asserted_operations(
    *, ontology: OntologyClosure
) -> dict[tuple[str, Iri, Iri], OntologyStatement]:
    """Translate the full verified selection or refuse unsupported RDF without discarding it."""
    operations: dict[tuple[str, Iri, Iri], OntologyStatement] = {}
    for parsed in ontology.documents:
        pin = parsed.document.pin
        for row in parsed.statements:
            if row.graph != pin.ontology_graph:
                continue
            if row.subject == pin.ontology_iri and (
                row.predicate in _HEADER_PREDICATES
                or (row.predicate == _TYPE and row.object == _ONTOLOGY)
            ):
                # SDK loading has already checked the declared identities and bound exact imports.
                continue
            if not isinstance(row.subject, Iri) or not isinstance(row.object, Iri):
                raise UnsupportedCapabilityError
            if row.predicate == _TYPE:
                kind = _DECLARATIONS.get(row.object, "member")
            elif (kind := _OPERATIONS.get(row.predicate)) is None:
                raise UnsupportedCapabilityError
            operations[kind, row.subject, row.object] = OntologyStatement(
                subject=row.subject, predicate=row.predicate, object=row.object
            )
    _require_named_classes(operations=operations)
    return operations


def _require_named_classes(*, operations: dict[tuple[str, Iri, Iri], OntologyStatement]) -> None:
    classes = {source for kind, source, _ in operations if kind == "class"} | _BUILTIN_CLASSES
    individuals = {source for kind, source, _ in operations if kind == "individual"}
    for kind, source, target in operations:
        if kind == "member" and (source not in individuals or target not in classes):
            raise UnsupportedCapabilityError
        if kind in _OPERATIONS.values() and (source not in classes or target not in classes):
            raise UnsupportedCapabilityError


def write_operations(
    *, operations: dict[tuple[str, Iri, Iri], OntologyStatement], path: Path
) -> None:
    """Send only validated class operations to the Java driver."""
    rows = sorted((kind, source.value, target.value) for kind, source, target in operations)
    _ = path.write_text("".join("\t".join(row) + "\n" for row in rows), encoding="utf-8")


@final
class RobotProcess:
    """Verify the pinned library and bound the isolated driver process."""

    def __init__(self, *, jar: Path) -> None:
        """Require the reviewed original JAR and a Java 17 or newer runtime."""
        self.jar = jar.resolve(strict=True)
        with self.jar.open("rb") as source:
            if (
                self.jar.stat().st_size != _ROBOT_SIZE
                or file_digest(source, "sha256").hexdigest() != ROBOT_SHA256
            ):
                raise ValueError("Restore the exact ROBOT 1.9.11 JAR before starting the engine.")
        home = os.environ.get("JAVA_HOME")
        java = which("java") if home is None else str(Path(home) / "bin/java")
        if java is None or not Path(java).is_file():
            raise ValueError("Install a Java 17 or newer runtime to run the formal engine.")
        self.java = Path(java).absolute()
        driver_hash = Hashing.hash_bytes(content=_DRIVER.read_bytes())
        self.version = f"1.9.11/HermiT-1.4.5.456/OWLAPI-4.5.29/{driver_hash.value}"

    async def run(self, *, task: str, source: Path, selection: Path, bytes_limit: int) -> bytes:
        """Read bounded structured output and reap Java on timeout or cancellation."""
        process = await asyncio.create_subprocess_exec(
            self.java,
            "-Xmx384m",
            "-XX:ActiveProcessorCount=2",
            "-Djava.net.useSystemProxies=false",
            "--class-path",
            self.jar,
            "--source",
            "17",
            _DRIVER,
            task,
            source,
            selection,
            cwd=source.parent,
            env={"PATH": str(self.java.parent)},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        captured = bytearray()
        try:
            if process.stdout is None:
                raise RuntimeError("Open the bounded Java output pipe.")
            while chunk := await process.stdout.read(65536):
                captured.extend(chunk)
                if len(captured) > bytes_limit:
                    raise ResourceLimitError
            if await process.wait() != 0:
                raise RuntimeError("The pinned Java driver failed.")
        finally:
            if process.returncode is None:
                process.kill()
                _ = await process.wait()
        return bytes(captured)


@final
class RobotReasoner:
    """Complete OWL Direct results within the driver's tested named-class fragment."""

    def __init__(self, *, jar: Path) -> None:
        """Capture the reviewed engine identity and tested restrictions."""
        self._process = RobotProcess(jar=jar)
        self.capabilities = OntologyCapabilities(
            adapter_id="robot/hermit",
            adapter_version=self._process.version,
            reasoning=tuple(
                ReasoningSupport(
                    profile=ReasoningProfile.OWL2_DL,
                    regime=SemanticRegime.OWL_DIRECT,
                    task=task,
                    complete=True,
                    restrictions=(
                        "named-class-hierarchies-equivalence-and-disjointness",
                        "named-individual-class-assertions",
                        "finite-named-class-subsumption",
                    ),
                )
                for task in ReasoningTask
            ),
        )

    async def reason(
        self, *, ontology: OntologyClosure, request: ReasoningRequest, limits: OntologyLimits
    ) -> ReasoningResult:
        """Check consistency first and keep derived subclass statements separate."""
        asserted = asserted_operations(ontology=ontology)
        selected = request.signature or tuple(
            term
            for item in ontology.documents
            for term in item.terms
            if term.entity_kind is OntologyEntityKind.CLASS
        )
        with TemporaryDirectory(prefix="domain-kernel-robot-") as folder:
            root = Path(folder)
            write_operations(operations=asserted, path=root / "asserted.tsv")
            query = {} if request.query is None else asserted_operations(ontology=request.query)
            if request.query is None:
                _ = (root / "selected.tsv").write_text(
                    "".join(
                        f"{iri}\n" for iri in sorted({term.term_iri.value for term in selected})
                    ),
                    encoding="utf-8",
                )
            else:
                write_operations(operations=query, path=root / "selected.tsv")
            response = await self._process.run(
                task=request.task.value,
                source=root / "asserted.tsv",
                selection=root / "selected.tsv",
                bytes_limit=limits.max_bytes,
            )
        status, *lines = response.decode("utf-8").splitlines()
        if status == "unsupported":
            raise UnsupportedCapabilityError
        if status not in {"consistent", "inconsistent", "entailed", "not_entailed"}:
            raise ValueError("Inspect the exact engine response format.")
        bottom, inferred = _hierarchy(lines=lines)
        if status == "entailed":
            inferred.update(row for key, row in query.items() if key[0] == "sub")
        inferred.difference_update(asserted.values())
        return ReasoningResult(
            input_hash=ontology.content_hash,
            request=request,
            adapter=self.capabilities,
            limits=limits,
            status=SemanticStatus.COMPLETE,
            consistent=status != "inconsistent",
            entailed={"entailed": True, "not_entailed": False}.get(status),
            unsatisfiable=tuple(
                dict.fromkeys(term for term in selected if term.term_iri.value in bottom)
            ),
            inferred=tuple(sorted(inferred, key=repr)),
            issues=(),
        )


def _hierarchy(*, lines: list[str]) -> tuple[set[str], set[OntologyStatement]]:
    bottom: set[str] = set()
    inferred: set[OntologyStatement] = set()
    for line in lines:
        match line.split("\t"):
            case ["bottom", iri]:
                bottom.add(iri)
            case ["sub", lower, upper]:
                inferred.add(
                    OntologyStatement(
                        subject=Iri(value=lower), predicate=_SUBCLASS, object=Iri(value=upper)
                    )
                )
            case _:
                raise ValueError("Inspect the exact engine classification format.")
    return bottom, inferred
