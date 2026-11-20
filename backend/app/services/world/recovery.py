"""Recovery projections over accepted relational work, without credentials."""
from app.database.world_frozen_repository import point_payload
from app.schemas.world.v2.contexts import RecoveryView


def recovery_view(connection, record, current_view, successor_view=None):
    """The caller validates lease token, current epoch and TTL before reading."""
    return RecoveryView.model_validate(dict(fenceEpoch=record['lease']['fenceEpoch'],
        current=point_payload(connection, record, current_view),
        successor=point_payload(connection, record, successor_view))).model_dump(mode='json')
