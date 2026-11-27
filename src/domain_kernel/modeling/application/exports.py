"""Deliver a verified publication with its exact portable bytes and metadata."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.modeling.application.contracts.export_payload import ExportPayload
from domain_kernel.shared.application.commands.deliver_artifact_command import (
    DeliverArtifactCommand,
)
from domain_kernel.shared.application.requests.artifact_write_request import ArtifactWriteRequest
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.domain.enums.audit_action import AuditAction
from domain_kernel.shared.domain.validators.path_validation import PathValidation
from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
from domain_kernel.shared.errors.source_read_error import SourceReadError
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from domain_kernel.bundles import DomainModelBundle
    from domain_kernel.shared.application.protocols.artifact_store import ArtifactStore
    from domain_kernel.shared.application.protocols.deliver_artifact import DeliverArtifact
    from domain_kernel.shared.domain.entities.artifact import Artifact


@dataclass(frozen=True, kw_only=True)
class ExportDestination:
    """An approved store with a stable configuration identity."""

    store: ArtifactStore
    binding: str


def bundle_payload(*, bundle: DomainModelBundle, request: object) -> ExportPayload:
    """Render complete canonical bundle bytes independent of the path suffix."""
    if request is not None:
        raise TypeError("Omit the request to deliver a complete model bundle")
    payload = bundle.serialize()
    return ExportPayload(
        media_type="application/json",
        content_hash=Hashing.hash_bytes(content=payload),
        chunks=(payload,),
    )


@dataclass(frozen=True, kw_only=True)
class PublicationExport:
    """The exact authorized publication and its caller's delivery intent."""

    actor: str
    bundle: DomainModelBundle
    store: str
    path: str
    idempotency_key: str | None

    def request(self, *, payload: ExportPayload) -> ArtifactWriteRequest:
        """Allocate a project-scoped key and carry its complete metadata."""
        scope = self.bundle.scope
        parts = PathValidation.relative_parts(path=self.path)
        if any(":" in part for part in parts):
            raise SourceReadError(message="Use a portable path in the configured artifact store.")
        return ArtifactWriteRequest(
            project_id=scope.project_id,
            model_id=scope.model_id,
            store=self.store,
            key="/".join(("projects", scope.project_id.value, *parts)),
            media_type=payload.media_type,
            expected_hash=payload.content_hash,
            projection_limits=payload.projection_limits,
            semantic=payload.semantic,
            schema=payload.schema,
            consumer_obligations=payload.consumer_obligations,
        )

    async def deliver(
        self,
        *,
        delivery: DeliverArtifact,
        destination: ExportDestination,
        payload: ExportPayload,
    ) -> Artifact:
        """Journal the exact request and verify its receipt outside the transaction."""
        request = self.request(payload=payload)
        store = destination.store

        async def write(*, retry: bool) -> Artifact:
            _ = retry
            try:
                return await asyncio.to_thread(store.put, request=request, chunks=payload.chunks)
            except OSError:
                raise SourceReadError(
                    message="Check access to the selected artifact store."
                ) from None

        async def verify(artifact: Artifact) -> bool:
            try:
                return await asyncio.to_thread(store.verify, artifact=artifact)
            except OSError:
                raise SourceReadError(
                    message="Check access to the selected artifact store."
                ) from None

        resource = AuditResource(
            resource_id=self.bundle.id,
            revision=None,
            content_hash=self.bundle.content_hash,
        )
        outcome = await delivery.deliver(
            request=DeliverArtifactCommand(
                action=AuditAction.EXPORT,
                actor=self.actor,
                idempotency_key=self.idempotency_key,
                intent=(
                    destination.binding,
                    RecordCodec.to_value(value=self.bundle.model_version),
                    RecordCodec.to_value(value=request, root_type=ArtifactWriteRequest),
                ),
                requested=request.to_artifact(),
                resource=resource,
            ),
            write=write,
            verify=verify,
        )
        return outcome.artifact
