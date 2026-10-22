"""Commit-time verification against the sealed prefix."""
from app.schemas.world.contracts import TimelinePoint

from .violations import KernelViolation, ViolationKind


def verify_point_binding(point: TimelinePoint, sealed_kind: str,
                         sealed_time_advance) -> None:
    """A commit must match the kind and time the sealed prefix reserved; T08 s9
    commits 3s against a 2s prefix and is refused with ``prefix_binding_mismatch``."""
    if (point.kind != sealed_kind
            or point.timeAdvance.boundary != sealed_time_advance.boundary
            or point.timeAdvance.duration.amount != sealed_time_advance.duration.amount
            or point.timeAdvance.duration.unit != sealed_time_advance.duration.unit):
        raise KernelViolation(
            ViolationKind.PREFIX_BINDING,
            f'point binds {point.kind}/{point.timeAdvance.duration.amount}'
            f'{point.timeAdvance.duration.unit} against sealed '
            f'{sealed_kind}/{sealed_time_advance.duration.amount}'
            f'{sealed_time_advance.duration.unit}')
