"""D/C handoff experiment. Receipts are supplied by A/B, never forged by D.

The orchestration below is an integration contract/test adapter, not a second
commit service. A/B remain the owners of validation, apply, persistence, dice,
leases and authoritative scheduling. Semantic result mappings stay transient.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from short_contracts import ContractError, FrozenValue, digest, exact_coverage, require_fields


def committed_packet(before, after, *, verify_committed):
    """Bind full saved Δ, before and after from one verified get_state lineage.

    verify_committed must validate the service provenance/digests and replay Δ
    with the existing authority. A candidate preview cannot stand in for it.
    """
    fields = ('pointId', 'version', 'state', 'stateDigest', 'previousPointId', 'timeAdvance', 'entityDeltas')
    require_fields(after, fields)
    if (type(after['version']) is not int or not 0 <= after['version'] <= 9007199254740991
            or not after['stateDigest']):
        raise ContractError('invalid_committed_anchor')
    if after['previousPointId'] is None:
        if before is not None or after['version'] != 0 or after['entityDeltas'] or after['timeAdvance'] is not None:
            raise ContractError('invalid_root_record')
    else:
        require_fields(before, fields)
        if type(before['version']) is not int or not 0 <= before['version'] <= 9007199254740991:
            raise ContractError('invalid_predecessor_version')
        if (before['pointId'] != after['previousPointId'] or before['version'] + 1 != after['version']
                or before['state']['worldId'] != after['state']['worldId'] or after['timeAdvance'] is None):
            raise ContractError('committed_lineage_mismatch')
        if before['state']['initial'] != after['state']['initial']:
            raise ContractError('initial_state_changed')
    if verify_committed is None or verify_committed(copy.deepcopy(before), copy.deepcopy(after)) is not True:
        raise ContractError('committed_provenance_or_replay_unverified')
    return FrozenValue({'anchor': {'worldId': after['state']['worldId'], 'pointId': after['pointId'],
                                  'version': after['version'], 'stateDigest': after['stateDigest'],
                                  'previousPointId': after['previousPointId']},
                        'before': None if before is None else before['state'],
                        'delta': {'timeAdvance': after['timeAdvance'], 'entityDeltas': after['entityDeltas']},
                        'after': after['state']})


class PointHandoff:
    """Explicit completion barriers; no component completion is a commit."""
    def __init__(self, binding, *, required_slots, required_units, time_scan_required):
        require_fields(binding, ('worldId', 'pointId', 'version', 'requestId', 'epoch', 'checkpointRevision'))
        if any(not isinstance(binding[k], str) or not binding[k].strip() for k in ('worldId', 'pointId', 'requestId')):
            raise ContractError('invalid_point_identity')
        for key in ('version', 'epoch', 'checkpointRevision'):
            minimum = 1 if key == 'epoch' else 0
            if type(binding[key]) is not int or not minimum <= binding[key] <= 9007199254740991:
                raise ContractError('invalid_point_binding_number:' + key)
        if type(time_scan_required) is not bool:
            raise ContractError('time_scan_requirement_must_be_explicit')
        self.binding = copy.deepcopy(binding)
        self.required_slots, self.required_units = list(required_slots), list(required_units)
        exact_coverage(self.required_slots, self.required_slots, 'slot_uniqueness')
        exact_coverage(self.required_units, self.required_units, 'unit_uniqueness')
        self.time_scan_required = bool(time_scan_required)
        self.slots, self.units, self.time_scanned = [], {}, False
        self.sealed, self.committed, self.packet = False, False, None
        self.claim_generation, self.narration_status = 0, 'not_started'
        self.cancelled = False
        self.frozen_actions, self.frozen_rolls = {}, {}
        self.events = []

    def _open(self):
        if self.cancelled or self.sealed or self.committed:
            raise ContractError('point_not_open')

    def _receipt(self, receipt, operation):
        require_fields(receipt, ('operation', 'worldId', 'pointId', 'version', 'requestId', 'epoch', 'checkpointRevision', 'nextCheckpointRevision', 'accepted'))
        if receipt['operation'] != operation or receipt['accepted'] is not True:
            raise ContractError('unaccepted_authority_receipt')
        if any(type(receipt[k]) is not type(self.binding[k]) or receipt[k] != self.binding[k]
               for k in ('worldId', 'pointId', 'version', 'requestId', 'epoch', 'checkpointRevision')):
            raise ContractError('stale_or_foreign_receipt')
        if (type(receipt['nextCheckpointRevision']) is not int
                or not self.binding['checkpointRevision'] < receipt['nextCheckpointRevision'] <= 9007199254740991):
            raise ContractError('nonadvancing_checkpoint_receipt')

    def _accept(self, receipt):
        self.binding['checkpointRevision'] = receipt['nextCheckpointRevision']

    def freeze(self, kind, key, value):
        self._open()
        if kind not in ('action', 'roll'):
            raise ContractError('invalid_frozen_kind')
        target = self.frozen_actions if kind == 'action' else self.frozen_rolls
        frozen = FrozenValue(value)
        if key in target and target[key].hash != frozen.hash:
            raise ContractError('frozen_work_rewrite')
        target[key] = frozen

    def slot_completed(self, slot_id, receipt):
        self._open()
        self._receipt(receipt, 'slot_completed')
        if receipt.get('slotId') != slot_id:
            raise ContractError('slot_receipt_target_mismatch')
        if slot_id not in self.required_slots or slot_id in self.slots:
            raise ContractError('unknown_or_duplicate_slot')
        self.slots.append(slot_id)
        self._accept(receipt)

    def unit_staged(self, unit_id, stages, candidates, receipt):
        self._open()
        self._receipt(receipt, 'checkpoint_stage_unit')
        if receipt.get('unitId') != unit_id:
            raise ContractError('unit_receipt_target_mismatch')
        if stages != ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity']:
            raise ContractError('six_stages_incomplete_or_reordered')
        if unit_id not in self.required_units or unit_id in self.units:
            raise ContractError('unknown_or_duplicate_unit')
        candidate_hash = digest(candidates)
        if receipt.get('candidateHash') != candidate_hash:
            raise ContractError('staged_candidate_receipt_mismatch')
        self.units[unit_id] = candidate_hash
        self._accept(receipt)
        self.events.append({'event': 'unit_staged', 'unitId': unit_id, 'candidateHash': candidate_hash})

    def time_scan_staged(self, candidates, receipt):
        self._open()
        self._receipt(receipt, 'checkpoint_stage_time_scan')
        if self.time_scanned or receipt.get('candidateHash') != digest(candidates):
            raise ContractError('duplicate_or_mismatched_time_scan')
        self.time_scanned = True
        self._accept(receipt)

    def seal(self, receipt):
        self._open()
        exact_coverage(self.slots, self.required_slots, 'point_slots')
        exact_coverage(self.units, self.required_units, 'point_units')
        if self.time_scan_required and not self.time_scanned:
            raise ContractError('time_scan_unfinished')
        self._receipt(receipt, 'checkpoint_seal_point')
        self.sealed = True
        self._accept(receipt)

    def commit(self, before, after, receipt, verify_committed):
        if not self.sealed or self.committed or self.cancelled:
            raise ContractError('commit_without_seal_or_repeated')
        self._receipt(receipt, 'commit_point')
        if after['pointId'] != self.binding['pointId'] or after['version'] != self.binding['version'] + 1:
            raise ContractError('commit_version_mismatch')
        packet = committed_packet(before, after, verify_committed=verify_committed)
        if packet.read()['anchor']['worldId'] != self.binding['worldId']:
            raise ContractError('commit_world_mismatch')
        self.packet, self.committed, self.narration_status = packet, True, 'pending'
        self._accept(receipt)

    def claim_narration(self):
        if not self.committed or self.cancelled or self.narration_status == 'ready':
            raise ContractError('narration_not_claimable')
        self.claim_generation += 1
        self.narration_status = 'pending'
        return {'binding': copy.deepcopy(self.binding), 'generation': self.claim_generation,
                'packetHash': self.packet.hash, 'facts': self.packet.read()}

    def narration_settled(self, claim, status):
        if status not in ('ready', 'failed', 'timeout', 'cancelled'):
            raise ContractError('invalid_narration_status')
        if (self.cancelled or not self.committed or claim.get('binding') != self.binding
                or claim.get('generation') != self.claim_generation or claim.get('packetHash') != self.packet.hash
                or self.narration_status != 'pending'):
            raise ContractError('stale_narration_completion')
        self.narration_status = status
        # No state rollback, re-roll, action generation or result generation here.

    def cancel_request(self):
        self.cancelled = True
        self.claim_generation += 1

    @property
    def ready(self):
        return self.committed and self.narration_status == 'ready' and not self.cancelled

    def snapshot(self):
        state = {k: copy.deepcopy(v) for k, v in self.__dict__.items()
                 if k not in ('packet', 'frozen_actions', 'frozen_rolls')}
        state.update(packet=None if self.packet is None else self.packet.read(),
                     frozen_actions={k: v.read() for k, v in self.frozen_actions.items()},
                     frozen_rolls={k: v.read() for k, v in self.frozen_rolls.items()})
        return {'schema': 'd-short-handoff-v1', 'state': state, 'sha256': digest(state)}

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Unique snapshots: an unfinished write remains diagnosable and is rejected.
        with path.open('x', encoding='utf-8') as stream:
            json.dump(self.snapshot(), stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())

    @classmethod
    def restore(cls, snapshot, *, expected_binding, verify_recovery):
        if (snapshot.get('schema') != 'd-short-handoff-v1'
                or snapshot.get('sha256') != digest(snapshot.get('state'))):
            raise ContractError('corrupt_handoff_snapshot')
        s = snapshot['state']
        if s['binding'] != expected_binding or verify_recovery(copy.deepcopy(s)) is not True:
            raise ContractError('stale_or_unverified_recovery')
        obj = cls(s['binding'], required_slots=s['required_slots'], required_units=s['required_units'],
                  time_scan_required=s['time_scan_required'])
        obj.__dict__.update(copy.deepcopy(s))
        obj.packet = None if s['packet'] is None else FrozenValue(s['packet'])
        obj.frozen_actions = {k: FrozenValue(v) for k, v in s['frozen_actions'].items()}
        obj.frozen_rolls = {k: FrozenValue(v) for k, v in s['frozen_rolls'].items()}
        # Pre-crash in-flight output must never open the restored gate.
        obj.claim_generation += 1
        if obj.narration_status == 'pending':
            obj.narration_status = 'failed'
        return obj
