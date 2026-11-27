from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from domain_kernel.modeling.application.baseline import initialize_copy, load_copy_source
from domain_kernel.modeling.application.dependencies import materialize_dependencies
from domain_kernel.modeling.application.protocols.manage_models import ManageModels
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.modeling.domain.models import ModelInfo
from domain_kernel.modeling.domain.snapshots import DomainModelBundle
from domain_kernel.reference_packs.api.packs import ReferencePack
from domain_kernel.reference_packs.domain.contracts import COVERAGE_VALIDATOR, ObligationKind
from domain_kernel.reference_packs.domain.errors.invalid_reference_pack_error import (
    InvalidReferencePackError,
)
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.domain.entities.audit_record import AuditRecord
from domain_kernel.shared.domain.enums.audit_action import AuditAction
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.domain.policies.lookup_naming_policy import LookupNamingPolicy
from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion
from domain_kernel.shared.errors.missing_capability_error import MissingCapabilityError
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.modeling.application.baseline import BaselineDefinitions
    from domain_kernel.modeling.application.commands.create_model import CreateModel
    from domain_kernel.modeling.application.dependencies import PublishedDependencies
    from domain_kernel.modeling.application.protocols.model_catalog import ModelCatalog
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.reference_packs.application.selection_ports import SelectedPacks
    from domain_kernel.shared.application.protocols.audit_repository import AuditRepository
    from domain_kernel.shared.application.protocols.transaction_manager import TransactionManager
    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor


@final
class ManageModelsService(ManageModels):
    """Use cases for creating and reopening independent model workspaces."""

    def __init__(  # noqa: PLR0913 - Bind the resources for one model operation.
        self,
        *,
        project_id: ProjectId,
        catalog: ModelCatalog,
        audit: AuditRepository,
        transaction: TransactionManager,
        packs: SelectedPacks | None = None,
        resolver: PublishedDependencies | None = None,
        baseline_definitions: BaselineDefinitions | None = None,
    ) -> None:
        """Bind a project and the capabilities for its operation."""
        self._project_id = project_id
        self._catalog = catalog
        self._audit = audit
        self._transaction = transaction
        self._packs = packs
        self._resolver = resolver
        self._baseline_definitions = baseline_definitions

    @override
    async def create(self, *, command: CreateModel) -> ModelInfo:
        """Store model intent, stable names and a creation audit event together."""
        TextValidation.require_text(value=command.actor, field="Actor")
        TextValidation.require_text(value=command.description, field="Model description")
        RuntimeTypeValidation.require_exact(
            value=command.kind, expected=ModelKind, field="Model kind"
        )
        if command.reference_pack is not None:
            ManageModelsService._validate_selection(pack=command.reference_pack)
            if self._packs is None:
                raise MissingCapabilityError(message="Configure durable selected-pack persistence")
        if command.copy_from is not None:
            RuntimeTypeValidation.require_exact(
                value=command.copy_from, expected=DomainModelBundle, field="Published copy source"
            )
        lookup_name, label = LookupNamingPolicy.resolve_names(
            name=command.name, display_name=command.display_name
        )
        scope = ModelScope(project_id=self._project_id, model_id=ModelId(value=uuid4().hex))
        pins = SequenceValidation.snapshot_sequence(
            items=command.dependencies, item_type=ModelVersion, field="Dependencies"
        )

        async with self._transaction.begin():
            source = None
            writer = self._baseline_definitions
            if command.copy_from is not None:
                if self._resolver is None or writer is None:
                    raise MissingCapabilityError(
                        message="Configure exact baseline copy persistence"
                    )
                source = await load_copy_source(
                    source=command.copy_from,
                    project_id=self._project_id,
                    releases=self._resolver,
                )
                inherited = source.publication.candidate.dependencies
                pins = (*inherited, *(pin for pin in pins if pin not in inherited))
            _ = await materialize_dependencies(resolver=self._resolver, scope=scope, pins=pins)
            info = ModelInfo(
                scope=scope,
                name=lookup_name,
                display_name=label,
                kind=command.kind,
                description=command.description,
                revision=0,
                reference_pack=None
                if command.reference_pack is None
                else command.reference_pack.pin,
                baseline=None if source is None else source.model_version,
                dependencies=pins,
                created_at=datetime.now(tz=UTC),
            )
            await self._catalog.create(info=info)
            if source is not None and writer is not None:
                await initialize_copy(scope=info.scope, source=source, writer=writer)
            if command.reference_pack is not None and self._packs is not None:
                await self._packs.attach(scope=info.scope, pack=command.reference_pack)
            await self._audit.append(
                record=ManageModelsService._created_model(info=info, actor=command.actor)
            )
            return info

    @override
    async def get(self, *, name: str) -> ModelInfo:
        """Read a named model from the bound project."""
        LookupNamingPolicy.require_lookup_name(name=name)
        async with self._transaction.begin():
            return await self._catalog.get(project_id=self._project_id, name=name)

    @override
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ModelInfo]:
        """Read detached model metadata from the bound project."""
        async with self._transaction.begin():
            return await self._catalog.list(project_id=self._project_id, limit=limit, cursor=cursor)

    @staticmethod
    def _validate_selection(*, pack: ReferencePack) -> None:
        """Require a valid reference pack whose mandatory validators are supported."""
        RuntimeTypeValidation.require_exact(
            value=pack, expected=ReferencePack, field="Selected reference pack"
        )
        validation = pack.validate()
        if not validation.valid:
            raise InvalidReferencePackError(issues=validation.issues)
        if any(
            item.required
            and (
                item.kind is not ObligationKind.COVERAGE or item.validator_id != COVERAGE_VALIDATOR
            )
            for item in pack.obligations
        ):
            raise MissingCapabilityError(message="Configure the required reference-pack validators")

    @staticmethod
    def _created_model(*, info: ModelInfo, actor: str) -> AuditRecord:
        """Record the attributed creation event and digest of its persisted model metadata."""
        pack = info.reference_pack
        resource = AuditResource(
            resource_id=info.scope.model_id,
            revision=info.revision,
            content_hash=Hashing.hash_json(
                value={
                    "project_id": info.scope.project_id.value,
                    "model_id": info.scope.model_id.value,
                    "name": info.name,
                    "display_name": info.display_name,
                    "kind": info.kind.value,
                    "description": info.description,
                    "revision": info.revision,
                    "reference_pack": None
                    if pack is None
                    else {
                        "key": pack.key,
                        "version": pack.version,
                        "content_hash": pack.content_hash.value,
                    },
                    "baseline": RecordCodec.to_value(value=info.baseline),
                    "dependencies": [
                        [pin.scope.model_id.value, pin.version, pin.content_hash.value]
                        for pin in info.dependencies
                    ],
                    "created_at": info.created_at.isoformat(),
                },
            ),
        )
        return AuditRecord(
            id=AuditId(value=uuid4().hex),
            project_id=info.scope.project_id,
            model_id=info.scope.model_id,
            action=AuditAction.CREATE_MODEL,
            outcome=AuditOutcome.SUCCEEDED,
            actor=actor,
            recorded_at=info.created_at,
            before=(),
            after=(resource,),
        )
