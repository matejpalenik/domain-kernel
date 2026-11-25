"""Read a selected passage from each verified original PDF with Docling."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from domain_kernel import (
    PDF,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    DoclingParser,
    DocumentSpan,
    ReaderLocation,
)
from domain_kernel.configuration import FilesystemReader, Retention
from examples.notebooks.host_capture import document_replay
from examples.notebooks.originals import load_originals


async def inspect_originals(*, directory: Path, models: Path) -> None:
    """Resolve the cited page and compare its selected text with the checked capture."""
    originals = await asyncio.to_thread(load_originals, directory=directory)
    _, passages = await asyncio.to_thread(document_replay)
    native = DoclingParser()
    ocr = DoclingParser(artifacts_path=models, ocr=True)

    with TemporaryDirectory(prefix="domain-kernel-originals-") as workspace:
        config = ClientConfiguration(
            base_dir=Path(workspace),
            readers=[FilesystemReader(name="inputs", root=directory)],
            retention=Retention(extracted_text=True),
        )
        _ = await Client(config=config).create_project(actor="demo:developer", name="originals")
        for lesson, _ in passages:
            parser = ocr if lesson.source_id == "wec" else native
            project = await Client(
                config=config, integrations=ClientIntegrations(format_parsers={"pdf": parser})
            ).get_project(name="originals")
            original = originals[lesson.source_id]
            received = await project.ingest_source(
                actor="demo:developer",
                name=lesson.source_id,
                source=PDF(
                    location=ReaderLocation(reader="inputs", path=original.relative_path),
                    expected_hash=original.digest,
                    pages=[lesson.page],
                ),
            )
            citation = next(
                evidence
                for evidence in received.evidence
                if isinstance(evidence.locator, DocumentSpan)
                and evidence.locator.page == lesson.page
                and evidence.locator.section is None
            )
            page = await project.get_evidence(evidence=citation)
            start = page.excerpt.index(lesson.text)
            end = start + len(lesson.text)
            _ = sys.stdout.write(
                f"{lesson.source_id} · PDF page {lesson.page} · span {start}:{end}\n"
                f"{received.revision.revision_id.value} · {citation.processing.parser_version}\n"
                f"{page.excerpt[start:end]}\n\n"
            )


class _Options(argparse.Namespace):
    originals: Path = Path()
    models: Path = Path()


def main() -> None:
    """Run the pinned parser recipe with explicitly provisioned inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--originals", type=Path, required=True)
    _ = parser.add_argument("--models", type=Path, required=True)
    options = parser.parse_args(namespace=_Options())
    asyncio.run(inspect_originals(directory=options.originals.resolve(), models=options.models))


if __name__ == "__main__":
    main()
