"""Replay: rebuild the state at a committed point by reapplying points.

The caller supplies the start state reconstructed from the canonical
projection (``get_state`` notes); this module only re-applies the committed
chain, so a digest match against the stored projection proves both the
chain and the encoding.
"""
from app.schemas.world.contracts import TimelinePoint, WorldState

from .apply import apply_point


def replay_world(start: WorldState, points: list[TimelinePoint]) -> WorldState:
    state = start
    for point in points:
        state = apply_point(state, point)
    return state
