"""Canonical projection definitions only; no world apply or state transitions."""
from typing import Literal
from pydantic import model_validator
from app.schemas.world.contracts import Contract, Id, TimeAdvance
from .contexts import BaselineView, WorkingProgress, SettledUnitView
from .work import SettlementGroup


class PrefixProjection(Contract):
    worldId: Id
    pointId: Id
    kind: Literal['normal','instant','linked']
    baseline: BaselineView
    timeAdvance: TimeAdvance
    timeLocked: Literal[True]
    working: WorkingProgress
    settledUnits: list[SettledUnitView]
    timeScanComplete: bool
    timeScanCandidates: SettlementGroup | None

    @model_validator(mode='after')
    def scan(self):
        if self.timeScanComplete != (self.timeScanCandidates is not None):
            raise ValueError('prefix scan marker and saved candidates differ')
        if self.timeScanCandidates is not None and self.timeScanCandidates.groupId is not None:
            raise ValueError('prefix scan cannot name an action group')
        return self


PREFIX_FIELDS=('pointId','kind','baseline','timeAdvance','timeLocked','working','settledUnits','timeScanComplete')


def prefix_projection(world_id, work, time_scan_candidates=None):
    """Exclude revision, paused, gate, credentials, successor and prefix itself.

    Saved unit contentHash binds each complete ordered candidate set. Verifying
    these hashes against authoritative accepted rows is an A1/A3 responsibility.
    """
    return PrefixProjection.model_validate({'worldId':world_id,
        **{key:work[key] for key in PREFIX_FIELDS},'timeScanCandidates':time_scan_candidates}).model_dump(mode='json')


def request_projection(operation, request):
    from .registry import OPERATION_BY_NAME
    from . import SCHEMA_MODELS
    spec=OPERATION_BY_NAME[operation]
    if spec.idempotency.scope=='none':raise ValueError('non-idempotent operation has no request hash projection')
    model=next(model for model in SCHEMA_MODELS if model.__name__==spec.requestSchema)
    return {'operation':operation,'request':model.model_validate(request).model_dump(mode='json')}
