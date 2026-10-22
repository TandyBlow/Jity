"""Pure structural predicates for the checkpoint control ladder.

Data-driven from the registry precondition matrix, so the predicates cannot
drift from the exported contract. Lease tokens, narration storage and gate
expiry stay with the A2 transaction (clock and credentials); frozenSource
belongs to A3 recovery. Everything decidable from the PointWorkView +
ControlState projection is enforced here. ``timeLocked`` and
``confirmedWork`` spell the same fact — both flip with the first confirmed
action/target/skip/time-scan in the same transaction.
"""
from app.schemas.world.v2.contexts import ControlState, PointWorkView
from app.schemas.world.v2.registry import OPERATION_BY_NAME

from .violations import Violation

_OPAQUE_KINDS = frozenset({'lease', 'headNarration', 'frozenSource', 'activeAdvance'})

# Local invariants the matrix rows omit: both operations mutate one point's
# time or slot record, which presumes an open work view even though their
# precondition rows carry no pointWork entry.
_OPEN_WORK_REQUIRED = frozenset({'checkpoint_set_point_time', 'checkpoint_record_skip'})


def check_checkpoint(operation: str, work: PointWorkView | None,
                     control: ControlState) -> tuple[Violation, ...]:
    """Structural violations for running ``operation`` at this projection;
    empty means every decidable precondition holds."""
    violations = []
    for pre in OPERATION_BY_NAME[operation].preconditions:
        if pre.kind in _OPAQUE_KINDS:
            continue
        if not _decide(pre.kind, pre.value, work, control):
            violations.append(Violation(
                pre.kind, f'{operation} requires {pre.kind}={pre.value!r}'))
    if operation in _OPEN_WORK_REQUIRED and (work is None or work.sealed):
        violations.append(Violation(
            'pointWork', f'{operation} requires an open work view'))
    return tuple(violations)


def _decide(kind: str, value, work: PointWorkView | None,
            control: ControlState) -> bool:
    if kind == 'phase':
        allowed = value if isinstance(value, list) else [value]
        return control.phase in allowed
    if kind == 'pointWork':
        states = value if isinstance(value, list) else [value]
        if work is None:
            return 'absent' in states
        return ('sealed' if work.sealed else 'open') in states
    if kind == 'activePendingGroup':
        present = work is not None and work.pendingGroup is not None
        return present if value == 'present' else not present
    if kind == 'settledUnits':
        return not (work.settledUnits if work else ())
    if kind in ('timeLocked', 'confirmedWork'):
        return not (work.timeLocked if work else False)
    if kind == 'paused':
        return control.paused == value
    if kind == 'gate':
        return control.gate.status == 'none'
    raise AssertionError(f'undecidable precondition kind {kind}')
