"""Preview: stateless recompute from the authoritative baseline.

Only the request's ``settlementGroups`` take part — staged units are never
double-counted, and the groupId-less time-scan unit rides in the same list:
there is no separate channel an extra parameter could double-count. The
byte-budget predicate mirrors registry notes: request 512 KiB, response
2 MiB, ``details.limit=request|response``; response bytes are measured by
the caller after serialization, never baked into the payload.
"""
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.contracts import TimelinePoint, WorldState
from app.schemas.world.v2.work import SettlementGroup, U5PreviewGroup
from app.schemas.world.v2.requests import PreviewPointRequest

from .apply import apply_point
from .merge import point_entity_deltas
from .state import state_digest

PREVIEW_REQUEST_LIMIT = 512 * 1024
PREVIEW_RESPONSE_LIMIT = 2 * 1024 * 1024


def preview_point(state: WorldState, point: TimelinePoint,
                  groups: list[SettlementGroup | U5PreviewGroup]) -> dict:
    # Revalidate even model instances: model_construct/copy must not bypass
    # final pair rules or the narrowly scoped intermediate marker.
    checked = []
    for index, group in enumerate(groups):
        raw = group.model_dump(mode='json') if hasattr(group, 'model_dump') else group
        if raw.get('previewStage') == 'U5':
            if index != len(groups) - 1:
                raise ValueError('U5 intermediate must be last')
            checked.append(U5PreviewGroup.model_validate(raw))
        else:
            checked.append(SettlementGroup.model_validate(raw))
    merged = point_entity_deltas(checked, None)
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
    }


def preview_over_budget(request_bytes: int,
                        response_bytes: int | None = None) -> tuple[str, int] | None:
    if request_bytes > PREVIEW_REQUEST_LIMIT:
        return ('request', PREVIEW_REQUEST_LIMIT)
    if response_bytes is not None and response_bytes > PREVIEW_RESPONSE_LIMIT:
        return ('response', PREVIEW_RESPONSE_LIMIT)
    return None


def preview_request(state: WorldState, point: TimelinePoint, payload: dict) -> dict:
    """Real request validation followed by stateless projection, never a write."""
    request = PreviewPointRequest.model_validate(payload)
    if request.worldId != state.worldId or request.pointId != point.id:
        raise ValueError('preview scope mismatch')
    if request.timeAdvance != point.timeAdvance:
        raise ValueError('preview time mismatch')
    return preview_point(state, point, request.settlementGroups)
