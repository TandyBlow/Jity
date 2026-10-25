"""Sealed-prefix reservations and atomic promotion of their saved work."""
from dataclasses import dataclass

from app.database.world_repository import LedgerMismatch
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.contracts import TimelinePoint, WorldState
from app.schemas.world.v2.projections import prefix_projection
from app.services.world.preview import preview_point
from app.services.world.state import state_digest
from app.services.world.units import WorkingProgress


def _refuse(detail, code='version_mismatch', reason='prefix_binding_mismatch'):
    from .control import ServiceRefusal
    raise ServiceRefusal(code,detail,{'reason':reason})


def baseline_state(record,work):
    baseline = work['baseline']
    if state_digest(record['state']) == baseline['stateDigest']:
        return record['state']
    current = record.get('work')
    if current is not None and current['pointId'] == work.get('_predecessorPointId'):
        predicted = forecast(record,current)
        if predicted['workingStateDigest'] == baseline['stateDigest']:
            return WorldState.model_validate(predicted['workingState'])
    saved = record['pointStates'].get(baseline['headPointId'])
    if saved is not None and saved['stateDigest'] == baseline['stateDigest']:
        return saved['state']
    raise LedgerMismatch('Working baseline state is missing or differs from its reservation')


def forecast(record,work):
    baseline = work['baseline']
    point = TimelinePoint.model_validate(dict(worldId=record['worldId'],id=work['pointId'],
        sequence=baseline['version'] + 1,kind=work['kind'],previousPointId=baseline['headPointId'],
        roundId=record['round']['roundId'],advanceId=record['advance']['advanceId'],
        trigger=record['round']['trigger'],linkedFromPointId=None if work['kind']=='normal'
        else baseline['headPointId'],timeAdvance=work['timeAdvance'],entityDeltas={}))
    groups = [unit['candidates'] for unit in work['units']]
    if work['timeScan'] is not None:
        groups.append(work['timeScan'])
    return preview_point(baseline_state(record,work),point,groups)


def _prefix(record,work):
    fields = dict(pointId=work['pointId'],kind=work['kind'],baseline=work['baseline'],
        timeAdvance=work['timeAdvance'],timeLocked=True,working=work['working'].model_dump(mode='json'),
        settledUnits=[{key:unit[key] for key in ('unitId','groupId','memberIds','contentHash')}
                      for unit in work['units']],timeScanComplete=work['timeScanComplete'])
    return canonical_digest(prefix_projection(record['worldId'],fields,work['timeScan']))


def handler_prepare_successor(store,record,request):
    from .control import _bind_expected,_bind_work_point,_check_lease,_ladder
    _check_lease(record,request)
    _bind_expected(record,request)
    _bind_work_point(record,request)
    current = record.get('work')
    _ladder(record,'checkpoint_prepare_successor',current)
    if record.get('_successorWork') is not None or current.get('successor') is not None:
        _refuse('Only one direct successor can be reserved','phase_invalid','successor_already_reserved')
    if not current['units'] and not current['timeScanComplete']:
        _refuse('An empty predecessor must save its complete time scan','phase_invalid','time_scan_missing')
    if request.successorPointId in record['points'] or request.successorPointId in (
            record['rootPointId'],current['pointId']):
        _refuse('Successor identity is already in use')
    time = request.timeAdvance
    if time.boundary != 'instant' or time.duration.amount != 0:
        _refuse('A reserved boundary successor must use instant/zero time','request_malformed','successor_time_invalid')
    connection = getattr(getattr(store,'_local',None),'connection',None)
    if connection is not None and getattr(store,'persistent',False):
        from app.database.world_judgment_repository import require_allocated
        require_allocated(connection,record['worldId'],request.successorPointId,'point',
                          (record['round']['roundId'],record['advance']['advanceId']))
    prediction = forecast(record,current)
    current['timeLocked'] = True
    current['sealed'] = True
    current['prefixDigest'] = _prefix(record,current)
    baseline = dict(headPointId=current['pointId'],version=record['version'] + 1,
                    stateDigest=prediction['workingStateDigest'])
    summary = dict(pointId=request.successorPointId,predecessorPointId=current['pointId'],
        timeAdvance=time.model_dump(mode='json'),expectedPredecessorVersion=record['version'] + 1,
        prefixDigest=current['prefixDigest'],expectedPredecessorStateDigest=prediction['workingStateDigest'],
        baseline=baseline)
    current['successor'] = summary
    progress = current['working'].model_dump(mode='json')
    progress['settledUnitIds'] = []
    record['_successorWork'] = dict(pointId=request.successorPointId,kind='instant',
        timeAdvance=time.model_dump(mode='json'),timeLocked=True,sealed=False,prefixDigest=None,
        predecessorWorkDigest=current['prefixDigest'],_predecessorPointId=current['pointId'],
        timeScanComplete=False,timeScan=None,baseline=baseline,phase='select_actor',
        working=WorkingProgress.model_validate(progress),units=[],pendingGroup=None,successor=None)
    record['control']['revision'] += 1
    return dict(pointId=current['pointId'],successorPointId=request.successorPointId,
                prefixDigest=current['prefixDigest'],successor=summary)


def validate_reservation(record):
    current,reserved = record.get('work'),record.get('_successorWork')
    if reserved is None:
        if current is not None and current.get('successor') is not None:
            raise LedgerMismatch('Successor summary has no independent reserved work')
        return
    if current is None or not current['sealed'] or current['pendingGroup'] is not None:
        raise LedgerMismatch('Reserved successor requires its sealed active predecessor')
    prediction = forecast(record,current)
    summary = current.get('successor')
    expected_baseline = dict(headPointId=current['pointId'],version=record['version'] + 1,
                             stateDigest=prediction['workingStateDigest'])
    if (summary is None or summary['pointId'] != reserved['pointId']
            or summary['predecessorPointId'] != current['pointId']
            or summary['expectedPredecessorVersion'] != record['version'] + 1
            or summary['expectedPredecessorStateDigest'] != prediction['workingStateDigest']
            or summary['baseline'] != expected_baseline or reserved['baseline'] != expected_baseline
            or summary['prefixDigest'] != _prefix(record,current)
            or current['prefixDigest'] != summary['prefixDigest']
            or reserved.get('predecessorWorkDigest') != summary['prefixDigest']
            or reserved.get('_predecessorPointId') != current['pointId']
            or summary['timeAdvance'] != reserved['timeAdvance']
            or reserved['timeAdvance']['boundary'] != 'instant'
            or reserved['timeAdvance']['duration']['amount'] != 0
            or not reserved['timeLocked'] or reserved['kind'] != 'instant'
            or reserved['sealed'] or reserved['units'] or reserved['timeScanComplete']
            or reserved['successor'] is not None or reserved['phase'] not in ('select_actor','build_group')):
        raise LedgerMismatch('Reserved successor identity, time, state or prefix binding differs')


@dataclass
class Selection:
    current: dict | None
    phase: str
    state: WorldState
    selected_reserved: bool = False
    reservation: dict | None = None


_BOUNDARY_OPERATIONS = frozenset({'checkpoint_discover_group','checkpoint_extend_group',
                                 'create_rolls','checkpoint_restore_group_work','preview_point'})


def select_operation(store,record,operation,request):
    reserved = record.get('_successorWork')
    if reserved is None:
        return None
    validate_reservation(record)
    current = record['work']
    selected = getattr(request,'pointId',None) == reserved['pointId']
    if operation == 'create_rolls':
        group = reserved.get('pendingGroup')
        selected = bool(group and any(roll.groupId == group['groupId'] for roll in request.rolls))
    selection = Selection(current,record['control']['phase'],record['state'],selected,reserved)
    if selected:
        if operation not in _BOUNDARY_OPERATIONS:
            _refuse('Reserved work cannot advance before its predecessor commits','phase_invalid',
                    'predecessor_not_committed')
        if (operation == 'checkpoint_extend_group' and request.admittedMember is not None) or (
                operation == 'preview_point' and request.settlementGroups):
            _refuse('Only the boundary source and its saved targets may precede the predecessor',
                    'phase_invalid','predecessor_not_committed')
        record['state'] = baseline_state(record,reserved)
        record['work'] = reserved
        record['control']['phase'] = reserved['phase']
    elif operation == 'commit_point':
        if request.pointId != current['pointId']:
            _refuse('Only the current sealed predecessor may commit')
    elif operation.startswith('checkpoint_') and operation not in (
            'checkpoint_pause','checkpoint_resume','checkpoint_restore_group_work'):
        # A prepare sealed this prefix. Boundary operations must explicitly
        # target its reserved point, rather than alter the predecessor.
        _refuse('The predecessor prefix is already sealed','phase_invalid','predecessor_sealed')
    return selection


def finish_operation(store,record,operation,request,data,selection):
    if selection is None:
        return data
    if selection.selected_reserved:
        record['_successorWork'] = record['work']
        record['work'] = selection.current
        record['state'] = selection.state
        record['control']['phase'] = selection.phase
        return data
    if data is None:
        return data
    if operation == 'commit_point':
        summary = selection.current['successor']
        if (record['headPointId'] != summary['predecessorPointId']
                or record['version'] != summary['expectedPredecessorVersion']
                or state_digest(record['state']) != summary['expectedPredecessorStateDigest']
                or selection.reservation['baseline'] != summary['baseline']):
            _refuse('Committed predecessor differs from its sealed successor reservation')
        promoted = record.pop('_successorWork')
        promoted.pop('_predecessorPointId',None)
        record['work'] = promoted
        record['control']['phase'] = promoted['phase']
    elif operation == 'round_conclusion_cancel':
        abandoned = record.pop('_successorWork',None)
        if abandoned and abandoned['pendingGroup']:
            data['abandonedGroupIds'] = sorted(set(data['abandonedGroupIds']) |
                                             {abandoned['pendingGroup']['groupId']})
    return data
