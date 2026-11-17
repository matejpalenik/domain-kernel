"""Verify a shipped business schema and its record in an independent offline process."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from domain_kernel.shared.hashing import canonical_json_bytes

if TYPE_CHECKING:
    from domain_kernel import Artifact
    from domain_kernel.shared.hashing import JsonValue

_CONSUMER = """
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote

from jsonschema import Draft202012Validator, FormatChecker

def offline(event, _args):
    if event.startswith("socket.") or event == "sqlite3.connect":
        raise RuntimeError("The schema consumer only uses shipped files.")

sys.addaudithook(offline)
payload = Path("contract.schema.json").read_bytes()
expected, document_iri = sys.argv[1:]
assert "sha256:" + hashlib.sha256(payload).hexdigest() == expected
schema = json.loads(payload, parse_float=Decimal)
assert schema["$id"] == document_iri
metadata = schema["x-domain-kernel"]
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())
root = schema["$defs"][unquote(schema["$ref"].removeprefix("#/$defs/"))]
properties = root["properties"]
record = json.loads(Path("record.json").read_bytes(), parse_float=Decimal)
if "@type" in properties:
    record["@type"] = properties["@type"]["const"]
validator.validate(record)
root_pin = metadata["root"]
root_entry = next(item for item in metadata["definitions"] if item["source"] == root_pin)
print(f"Independent schema consumer accepted: {root_entry['name']}")
if "intended-purpose" in properties:
    purpose = properties["intended-purpose"]
    print(f"Intended purpose item bounds: {purpose['minItems']}..{purpose['maxItems']}")
    print(f"Actor relationships captured: {sum(name.startswith('rel:') for name in properties)}")
if metadata["units"]:
    unit = metadata["units"][0]
    print(f"Reusable unit: {unit['name']} ({unit['body']['symbol']})")
    print(f"Closed unit code: {metadata['unit_bindings'][0]['code']}")
    print(f"External quantity kind: {root_entry['body']['quantity']['quantity_kind']}")
"""


def inspect_json_schema_delivery(
    *, artifact: Artifact, path: Path, record: dict[str, JsonValue]
) -> str:
    """Transfer the saved schema, expected hash and sample record to a consumer."""
    if artifact.schema is None:
        raise TypeError("Deliver an artifact with exact schema metadata")
    with TemporaryDirectory(prefix="recruitment-schema-delivery-") as destination:
        folder = Path(destination)
        _ = (folder / "contract.schema.json").write_bytes(path.read_bytes())
        _ = (folder / "record.json").write_bytes(canonical_json_bytes(value=record))
        result = subprocess.run(  # noqa: S603 - Run fixed consumer code with exact file metadata.
            [
                sys.executable,
                "-I",
                "-c",
                _CONSUMER,
                artifact.content_hash.value,
                artifact.schema.document_iri.value,
            ],
            cwd=folder,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    return result.stdout
