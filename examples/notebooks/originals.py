"""Provision and verify the original files used by the recruitment notebook."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from urllib.request import urlopen

from pydantic import BaseModel

from domain_kernel import ContentHash
from domain_kernel.shared.hashing import hash_bytes

if TYPE_CHECKING:
    from typing import BinaryIO

ORIGINALS_ENV = "DOMAIN_KERNEL_TOUR_ORIGINALS"
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
    if not payload.startswith(b"%PDF-"):
        raise ValueError("Provide the pinned original PDF file.")
    return payload


def _acquire(*, asset: _Asset) -> bytes:
    if urlsplit(asset.url).scheme != "https":
        raise ValueError("Use a reviewed HTTPS original source.")
    with urlopen(asset.url, timeout=30) as response:  # noqa: S310 - Checked-in HTTPS publisher URLs.
        if urlsplit(response.geturl()).scheme != "https":
            raise ValueError("Keep publisher acquisition on HTTPS.")
        return _read(data=response, asset=asset)


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
                _ = _read(data=source, asset=asset)
        except FileNotFoundError:
            message = f"Provision the pinned {identifier} original in {relative_path}."
            raise ValueError(message) from None
        result[identifier] = Original(
            relative_path=relative_path,
            digest=ContentHash(value=f"sha256:{asset.sha256}"),
        )
    return result


def main() -> None:
    """Verify local inputs or explicitly acquire the originals from their publishers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--download", action="store_true")
    options = parser.parse_args()
    originals = load_originals(directory=options.directory, download=bool(options.download))
    for identifier, original in originals.items():
        _ = sys.stdout.write(f"{identifier} {original.digest.value} {original.relative_path}\n")


if __name__ == "__main__":
    main()
