"""Load transferred RDF documents and source pins in a separate offline consumer."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from domain_kernel.shared.hashing import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel import Artifact, Iri, RdfSyntax, SemanticProjection

_CONSUMER = """
import hashlib
import json
from pathlib import Path
import sys

from rdflib import Dataset, URIRef
from rdflib.namespace import PROV

def offline(event, _args):
    if event.startswith("socket.") or event == "sqlite3.connect":
        raise RuntimeError("This consumer only reads shipped documents.")

def pinned_bytes(entry):
    payload = Path(entry["file"]).read_bytes()
    assert "sha256:" + hashlib.sha256(payload).hexdigest() == entry["hash"]
    return payload

sys.addaudithook(offline)
manifest = json.loads(Path("transfer.json").read_bytes())
dataset = Dataset()
graphs = {}
for document in manifest["documents"]:
    selected = dataset.graph(identifier=URIRef(document["graph"]))
    selected.parse(data=pinned_bytes(document), format=document["syntax"])
    graphs[document["role"]] = selected
for source in manifest["source_documents"]:
    pinned_bytes(source)
ontology = graphs["ontology"]
metadata = graphs["model_metadata"]
model_shapes = graphs["model_shapes"]
instance_shapes = graphs["instance_shapes"]
local = tuple(URIRef(item) for item in manifest["local_specialization"])
external = manifest["external_specialization"]
print(f"Independent consumer found local specialization: {local in ontology}")
if external is not None:
    external = tuple(URIRef(item) for item in external)
    print(f"Independent consumer found original external term: {external in ontology}")
else:
    print("Independent consumer inspected the local specialization.")
attributed = any(metadata.triples((None, PROV.wasAttributedTo, None)))
print(f"Published attribution in metadata: {attributed}")
print(f"Both shape graph roles loaded: {bool(model_shapes) and bool(instance_shapes)}")
print(f"Original ontology closure documents verified: {len(manifest['source_documents'])}")
"""


def inspect_semantic_delivery(
    *,
    projection: SemanticProjection,
    artifacts: Sequence[tuple[Artifact, Path, RdfSyntax]],
    local_specialization: tuple[Iri, Iri, Iri],
    external_specialization: tuple[Iri, Iri, Iri] | None,
) -> str:
    """Transfer mapped graphs, exact exported bytes and the original adopted documents."""
    delivered = {
        artifact.semantic.role: (artifact, path, syntax)
        for artifact, path, syntax in artifacts
        if artifact.semantic is not None
    }
    with TemporaryDirectory(prefix="recruitment-rdf-delivery-") as receiver:
        target = Path(receiver)
        documents: list[dict[str, str]] = []
        for document in projection.documents:
            if document.model != projection.model:
                continue
            supplied = delivered.get(document.role)
            if supplied is None:
                payload, digest, syntax = (
                    document.payload,
                    document.content_hash,
                    "turtle" if document.syntax.value == "turtle" else "json-ld",
                )
            else:
                artifact, original, declared_syntax = supplied
                if (
                    artifact.semantic is None
                    or artifact.semantic.graph_iri != document.graph_iri
                    or artifact.semantic.model != document.model
                ):
                    raise ValueError("Deliver the declared snapshot and graph role")
                payload, digest = original.read_bytes(), artifact.content_hash
                syntax = "turtle" if declared_syntax.value == "turtle" else "json-ld"
            filename = f"{document.role.value}.rdf"
            _ = (target / filename).write_bytes(payload)
            documents.append(
                {
                    "file": filename,
                    "graph": document.graph_iri.value,
                    "hash": digest.value,
                    "role": document.role.value,
                    "syntax": syntax,
                }
            )
        origins: list[dict[str, str]] = []
        for closure in projection.ontologies:
            for parsed in closure.documents:
                filename = f"original-{len(origins)}.rdf"
                _ = (target / filename).write_bytes(parsed.document.payload)
                origins.append({"file": filename, "hash": parsed.document.pin.content_hash.value})
        _ = (target / "transfer.json").write_bytes(
            canonical_json_bytes(
                value={
                    "documents": documents,
                    "source_documents": origins,
                    "local_specialization": tuple(item.value for item in local_specialization),
                    "external_specialization": None
                    if external_specialization is None
                    else tuple(item.value for item in external_specialization),
                },
            )
        )
        process = subprocess.run(  # noqa: S603 - Fixed interpreter and offline consumer code.
            [sys.executable, "-I", "-c", _CONSUMER],
            cwd=target,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return process.stdout
