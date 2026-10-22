"""Preview: stateless recompute from the authoritative baseline.

Only the request's ``settlementGroups`` take part — staged units are never
double-counted (an append-type change previewed twice must appear once).
The byte-budget predicate mirrors registry notes: request 512 KiB,
response 2 MiB, ``details.limit=request|response``.
"""
from app.schemas.world.canonical import canonical_bytes, canonical_digest
from app.schemas.world.contracts import TimelinePoint, WorldState
from app.schemas.world.v2.work import SettlementGroup

from .apply import apply_point
from .merge import point_entity_deltas
from .state import state_digest

PREVIEW_REQUEST_LIMIT = 512 * 1024
PREVIEW_RESPONSE_LIMIT = 2 * 1024 * 1024


def preview_point(state: WorldState, point: TimelinePoint,
                  groups: list[SettlementGroup],
                  time_scan: SettlementGroup | None) -> dict:
    merged = point_entity_deltas(groups, time_scan)
    projection = point.model_copy(update={'entityDeltas': merged})
    working = apply_point(state, projection)
    projection_json = projection.model_dump(mode='json')
    return {
        'pointId': projection.id,
        'pointProjection': projection_json,
        'mergedEntityDeltas': {key: delta.model_dump(mode='json')
                               for key, delta in merged.items()},
        'workingState': working.model_dump(mode='json'),
        'workingStateDigest': state_digest(working),
        'pointProjectionDigest': canonical_digest(projection_json),
        '_projection_bytes': len(canonical_bytes(projection_json)),
    }


def preview_over_budget(request_bytes: int,
                        response_bytes: int | None = None) -> tuple[str, int] | None:
    if request_bytes > PREVIEW_REQUEST_LIMIT:
        return ('request', PREVIEW_REQUEST_LIMIT)
    if response_bytes is not None and response_bytes > PREVIEW_RESPONSE_LIMIT:
        return ('response', PREVIEW_RESPONSE_LIMIT)
    return None
