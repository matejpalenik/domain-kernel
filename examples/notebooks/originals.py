"""Provision and verify the original files used by the recruitment notebook."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit
from urllib.request import urlopen

from pydantic import BaseModel

from domain_kernel import ContentHash, Iri, OntologyDocument, OntologyDocumentPin, OntologySyntax
from domain_kernel.shared.hashing import hash_bytes

if TYPE_CHECKING:
    from typing import BinaryIO

ORIGINALS_ENV = "DOMAIN_KERNEL_TOUR_ORIGINALS"
ONTOLOGIES_ENV = "DOMAIN_KERNEL_TOUR_ONTOLOGIES"
LOMO_ENV = "DOMAIN_KERNEL_TOUR_LOMO"
TABULAR_ENV = "DOMAIN_KERNEL_TOUR_TABULAR"
type OntologyGroup = Literal["ontologies", "lomo"]
_LAYOUT = {
    "ai-act-en": "official/ai-act-en.pdf",
    "ai-act-fr": "official/translations/ai-act-fr.pdf",
    "guidance": "interpretation/guidance.pdf",
    "wec": "stakeholder/wec.pdf",
}


class _Asset(BaseModel):
    id: str
    url: str
    size: int
    sha256: str


class _Manifest(BaseModel):
    assets: list[_Asset]


class _RdfAsset(_Asset):
    relative_path: str
    groups: tuple[OntologyGroup, ...]
    document_iri: str
    ontology_iri: str | None = None
    version_iri: str | None = None
    syntax: OntologySyntax


class _RdfManifest(BaseModel):
    assets: list[_RdfAsset]


@dataclass(frozen=True, kw_only=True)
class Original:
    """One exact original in the approved relative fixture tree."""

    relative_path: str
    digest: ContentHash


def _read(*, data: BinaryIO, asset: _Asset) -> bytes:
    payload = data.read(asset.size + 1)
    if len(payload) != asset.size or hash_bytes(content=payload).value != f"sha256:{asset.sha256}":
        message = f"Provide the original {asset.id} bytes matching the acquisition manifest."
        raise ValueError(message)
    return payload


def _acquire(*, asset: _Asset) -> bytes:
    if urlsplit(asset.url).scheme != "https":
        raise ValueError("Use a reviewed HTTPS original source.")
    with urlopen(asset.url, timeout=30) as response:  # noqa: S310 - Checked-in HTTPS publisher URLs.
        if urlsplit(response.geturl()).scheme != "https":
            raise ValueError("Keep publisher acquisition on HTTPS.")
        return _read(data=response, asset=asset)


def _read_original(
    *,
    root: Path,
    relative_path: str,
    asset: _Asset,
    download: bool,
) -> bytes:
    path = root
    for part in Path(relative_path).parts:
        path /= part
        if path.is_symlink() or path.is_junction():
            raise ValueError("Provide regular original fixture files without links.")
    if download and not path.exists():
        payload = _acquire(asset=asset)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as destination:
            _ = destination.write(payload)
    try:
        with path.open("rb") as source:
            return _read(data=source, asset=asset)
    except FileNotFoundError:
        message = f"Provision the pinned {asset.id} original in {relative_path}."
        raise ValueError(message) from None


def load_ontology_inputs(
    *,
    directory: Path,
    group: OntologyGroup,
    download: bool = False,
) -> dict[str, OntologyDocument]:
    """Read exact pinned semantic originals from the selected source group."""
    manifest = _RdfManifest.model_validate_json(
        (Path(__file__).parent / "fixtures/ontology-acquisition.json").read_bytes(),
    )
    root = directory.resolve()
    result: dict[str, OntologyDocument] = {}
    for asset in manifest.assets:
        if group in asset.groups:
            result[asset.id] = OntologyDocument(
                pin=OntologyDocumentPin(
                    document_iri=Iri(value=asset.document_iri),
                    ontology_iri=Iri(value=asset.ontology_iri) if asset.ontology_iri else None,
                    version_iri=Iri(value=asset.version_iri) if asset.version_iri else None,
                    content_hash=ContentHash(value=f"sha256:{asset.sha256}"),
                ),
                syntax=asset.syntax,
                payload=_read_original(
                    root=root,
                    relative_path=asset.relative_path,
                    asset=asset,
                    download=download,
                ),
            )
    return result


def load_originals(*, directory: Path, download: bool = False) -> dict[str, Original]:
    """Verify the complete pinned input tree without substituting a newer edition."""
    manifest = _Manifest.model_validate_json(
        (Path(__file__).parent / "fixtures/acquisition.json").read_bytes(),
    )
    by_id = {item.id: item for item in manifest.assets}
    result: dict[str, Original] = {}
    root = directory.resolve()
    for identifier, relative_path in _LAYOUT.items():
        asset = by_id[identifier]
        if not _read_original(
            root=root,
            relative_path=relative_path,
            asset=asset,
            download=download,
        ).startswith(b"%PDF-"):
            raise ValueError("Provide the pinned original PDF file.")
        result[identifier] = Original(
            relative_path=relative_path,
            digest=ContentHash(value=f"sha256:{asset.sha256}"),
        )
    return result


def load_eli_workbook(*, directory: Path, download: bool = False) -> Original:
    """Verify the publisher workbook selected for the ELI table lesson."""
    manifest = _Manifest.model_validate_json(
        (Path(__file__).parent / "fixtures/acquisition.json").read_bytes(),
    )
    asset = next(item for item in manifest.assets if item.id == "eli-workbook")
    relative_path = "semantic/eli_ontology.xlsx"
    _ = _read_original(
        root=directory.resolve(),
        relative_path=relative_path,
        asset=asset,
        download=download,
    )
    return Original(relative_path=relative_path, digest=ContentHash(value=f"sha256:{asset.sha256}"))


def read_eli_selection() -> bytes:
    """Return the checked derivative for offline profiling."""
    return (Path(__file__).parent / "fixtures/eli-metadata-selection.csv").read_bytes()


def main() -> None:
    """Verify local inputs or explicitly acquire the originals from their publishers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--group", choices=("pdf", "ontologies", "lomo", "tabular"), default="pdf")
    options = parser.parse_args()
    group: str = str(options.group)
    if group == "tabular":
        workbook = load_eli_workbook(directory=options.directory, download=bool(options.download))
        _ = sys.stdout.write(f"eli-workbook {workbook.digest.value} {workbook.relative_path}\n")
        return
    if group in ("ontologies", "lomo"):
        selected: OntologyGroup = "lomo" if group == "lomo" else "ontologies"
        for identifier, document in load_ontology_inputs(
            directory=options.directory,
            group=selected,
            download=bool(options.download),
        ).items():
            _ = sys.stdout.write(f"{identifier} {document.pin.content_hash.value}\n")
        return
    originals = load_originals(directory=options.directory, download=bool(options.download))
    for identifier, original in originals.items():
        _ = sys.stdout.write(f"{identifier} {original.digest.value} {original.relative_path}\n")


if __name__ == "__main__":
    main()
