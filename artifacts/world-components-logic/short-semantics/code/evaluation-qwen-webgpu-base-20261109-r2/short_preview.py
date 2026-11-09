"""Read-only, pinned A official-preview adapter for OFFLINE D phase experiments.

No service, database, lease, checkpoint, commit or C narration is invoked.
The caller supplies a registered point/time context; nothing guesses time.
A's original preview/merge/apply and complete-unit validation source is read
from verified retained snapshots or bounded Git reads and executed unchanged. Partial previews deliberately
do not run complete-unit adoption rules until all six stages are present.
"""
from __future__ import annotations

import builtins
import copy
import json
import hashlib
import importlib
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

from short_contracts import ContractError, digest, result, incomplete
from short_settlement import STAGES

ROOT = Path(__file__).resolve().parents[2]
A_COMMIT = 'fc60a603c7e0b57805fffea0458192bcfebf6ffc'
A_FILES = {
    'backend/app/schemas/world/contracts.py': '97b0b59b727761565fed1873ded256e3698b49049aae31ce9a5ca6e6f16f4a9c',
    'backend/app/schemas/world/canonical.py': '2c2dd4de9fb743d8932d59b9b04e246c5dceda2d61844649732762384b9cfca1',
    'backend/app/schemas/world/v2/base.py': 'edfe307e68f363e83090bcc5dcced3dfb0033c5c1fdba6b81061a398422b5df8',
    'backend/app/schemas/world/v2/judgments.py': '48529d906cd93372c32870ba55a40ee420cb0fc2c93bf81d411cfa5101253ad9',
    'backend/app/schemas/world/v2/work.py': '3e8eebd8e285f872831ae21bf15c2c9678836dd13d77310f57beeeea805a1e31',
    'backend/app/schemas/world/v2/contexts.py': '18c4c37fd7b16726122decbe6ff5bec3d54c6e83baa4a33fe368515249e95a6c',
    'backend/app/services/world/violations.py': '84b8a529cb688675f2a7e12da7ed0f84838f58c182f81f1234065644c8fd5e7e',
    'backend/app/services/world/timing.py': '3dfd9c8072177dd26cf8875fe0b09881af41f56c3124bea2a60ca29d4d4b2407',
    'backend/app/services/world/apply.py': 'e626fdbb0679ca0cff73053f06b5887bf8a8a0f42280219fdd94b8e4b257af66',
    'backend/app/services/world/state.py': 'b13ce5de770e7be883bae03ad682482f097393b597dce7e8d117b151df0a1ed6',
    'backend/app/services/world/merge.py': 'dbe5fb4b22c62d0bc6bc86599c84227528cb9a636e5728021ad44d748a4647c4',
    'backend/app/services/world/preview.py': '55e7852e74b0db0de9b213833155b33d3577cb8388f43d0c31bd7f4e63fd888d',
    'backend/app/services/world/units.py': '9f8f080fed827352faa984d381f1d2f0868b789e063d2038939ddf2588111753',
}
AUTHORITY_SNAPSHOT = ROOT / 'artifacts/world-components-logic/short-semantics/code/evaluation-short-all-eval-20261109-r5/authority'
AUTHORITY_CACHE = Path.home() / '.cache/jity-d-short-semantics-20261109/authority' / A_COMMIT
GIT_SOURCE_TIMEOUT_SECONDS = 5
AUTHORITY_REMOTE = 'https://raw.githubusercontent.com/TandyBlow/Jity/' + A_COMMIT + '/'
_SNAPSHOT_CACHE = None
_SOURCE_LOCK = threading.RLock()
_SOURCE_READS = {}
_NAMESPACE = '_jity_d_offline_a_fc60a603'
_FIELDS = dict(zip(STAGES, ('positionSet', 'appearanceChanges', 'tasksAchieved',
                           'subtasksAdded', 'personalityChanges', 'sanitySet')))
_WIRE_FIELDS = dict(zip(STAGES, ('positions', 'appearances', 'tasksAchieved',
                                'subtasksAdded', 'personalities', 'sanities')))


def _require(ok, reason):
    if not ok:
        raise ContractError(reason)


def _source_path(path, expected_sha256=None):
    _require(isinstance(path, str) and path in A_FILES, 'unregistered_A_authority_path')
    _require(expected_sha256 is None or expected_sha256 == A_FILES[path], 'A_authority_expected_hash_mismatch')
    return A_FILES[path]


def _read_file_bounded(path):
    # macOS cloud placeholders can block an ordinary read despite a valid stat.
    # Bound that read in a child, without changing Cloud settings or Git files.
    return subprocess.check_output([sys.executable, '-I', '-S', '-c',
        'import sys; sys.stdout.buffer.write(open(sys.argv[1], "rb").read(1048577))', str(path)],
        stderr=subprocess.PIPE, timeout=GIT_SOURCE_TIMEOUT_SECONDS)


def _fetch_pinned_source(path):
    _source_path(path)
    # Only the exact fixed public commit/path is allowed, with a final SHA gate.
    return subprocess.check_output(['curl', '--fail', '--silent', '--show-error', '--location',
        '--max-time', str(GIT_SOURCE_TIMEOUT_SECONDS), '--max-filesize', '1048576',
        AUTHORITY_REMOTE + path], stderr=subprocess.PIPE, timeout=GIT_SOURCE_TIMEOUT_SECONDS + 1)


def _cache_verified_source(path, source, origin):
    destination = AUTHORITY_CACHE / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        observed = _read_file_bounded(destination)
        _require(hashlib.sha256(observed).hexdigest() == A_FILES[path], 'cached_A_source_hash_mismatch:' + path)
        return
    # The directory is specific to this experiment and this exact commit.
    # Exclusive writes never replace old bytes or any Git object.
    with destination.open('xb') as stream:
        stream.write(source); stream.flush(); os.fsync(stream.fileno())
    provenance = destination.with_name(destination.name + '.source.json')
    with provenance.open('x', encoding='utf-8') as stream:
        json.dump(origin, stream, ensure_ascii=False, sort_keys=True)


def _verified_snapshot():
    """Cache only after *all thirteen* original files pass their fixed hashes.

    Cached bytes are immutable and bound to commit/path/hash. Later filesystem
    edits cannot alter these retained bytes; a new process verifies anew. No
    existence flag, Git metadata or previous report substitutes for actual reads.
    """
    global _SNAPSHOT_CACHE
    key = (str(AUTHORITY_SNAPSHOT.resolve()), str(AUTHORITY_CACHE.resolve()), A_COMMIT, digest(A_FILES))
    with _SOURCE_LOCK:
        if _SNAPSHOT_CACHE is not None and _SNAPSHOT_CACHE[0] == key:
            return _SNAPSHOT_CACHE[1]
        bundle, origins = {}, {}
        for path, expected in A_FILES.items():
            cache = AUTHORITY_CACHE / path
            try:
                if cache.exists():
                    source = _read_file_bounded(cache)
                    origin = {'source': 'verified_pinned_cache', 'path': str(cache)}
                    provenance = cache.with_name(cache.name + '.source.json')
                    if provenance.exists(): origin['acquisition'] = json.loads(_read_file_bounded(provenance))
                else:
                    try:
                        source = _read_file_bounded(AUTHORITY_SNAPSHOT / path)
                        origin = {'source': 'retained_verified_snapshot', 'path': str(AUTHORITY_SNAPSHOT / path)}
                    except (OSError, subprocess.SubprocessError) as snapshot_error:
                        source = _fetch_pinned_source(path)
                        origin = {'source': 'pinned_remote_sha256', 'url': AUTHORITY_REMOTE + path,
                                  'snapshotReadFailure': type(snapshot_error).__name__}
            except (OSError, subprocess.SubprocessError) as error:
                raise ContractError('verified_A_source_unavailable:' + path + ':' + type(error).__name__) from error
            _require(hashlib.sha256(source).hexdigest() == expected,
                     'retained_A_snapshot_or_cache_hash_mismatch:' + path)
            origin.update(sourceCommit=A_COMMIT, sha256=expected, bytes=len(source))
            if not cache.exists():
                _cache_verified_source(path, source, origin)
                # Stable identity across freeze/worker processes: the newly
                # persisted exact-byte cache and its original acquisition are
                # represented just as on a subsequent verified cache read.
                origin = {'source': 'verified_pinned_cache', 'path': str(cache),
                          'acquisition': origin, 'sourceCommit': A_COMMIT,
                          'sha256': expected, 'bytes': len(source)}
            bundle[path] = source
            origins[path] = origin
        _require(len(bundle) == 13, 'incomplete_A_authority_snapshot')
        _SNAPSHOT_CACHE = (key, bundle, origins)
        return bundle


def read_authority_source(path, *, prefer_snapshot=True, expected_sha256=None):
    """Read unchanged pinned A source; never repair Git or hydrate by mutation.

    Default reads the complete retained, hash-verified r5 snapshot. Explicit Git
    reads have a five-second bound and fall back only to those same verified
    bytes. Unknown paths, differing expected hashes, missing/corrupt snapshots,
    or unavailable sources are failures, never synthesized authority code.
    """
    expected = _source_path(path, expected_sha256)
    _require(type(prefer_snapshot) is bool, 'invalid_A_source_preference')
    failure = None
    if not prefer_snapshot:
        try:
            source = subprocess.check_output(['git', 'show', A_COMMIT + ':' + path], cwd=ROOT,
                                             stderr=subprocess.PIPE, timeout=GIT_SOURCE_TIMEOUT_SECONDS)
            _require(hashlib.sha256(source).hexdigest() == expected, 'git_A_source_hash_mismatch:' + path)
            origin = 'git'
        except (OSError, subprocess.SubprocessError, ContractError) as error:
            failure = {'type': type(error).__name__, 'message': str(error)}
            source = _verified_snapshot()[path]
            origin = _SNAPSHOT_CACHE[2][path]['source']
    else:
        source = _verified_snapshot()[path]
        origin = _SNAPSHOT_CACHE[2][path]['source']
    receipt = {'source': origin, 'sourceCommit': A_COMMIT, 'path': path, 'sha256': expected,
               'bytes': len(source), 'gitTimeoutSeconds': GIT_SOURCE_TIMEOUT_SECONDS,
               'snapshotRoot': str(AUTHORITY_SNAPSHOT) if origin == 'retained_verified_snapshot' else None}
    if origin != 'git': receipt['retrieval'] = copy.deepcopy(_SNAPSHOT_CACHE[2][path])
    if failure is not None: receipt['gitFailure'] = failure
    with _SOURCE_LOCK: _SOURCE_READS[path] = receipt
    return source


def authority_source_reads():
    """Bounded last-read receipts; callers may persist them in their journal."""
    with _SOURCE_LOCK: return copy.deepcopy(_SOURCE_READS)


def _git_source(path, expected_sha256=None):
    """Compatibility name for bounded Git first, strict retained fallback."""
    return read_authority_source(path, prefer_snapshot=False, expected_sha256=expected_sha256)


def _load_kernel():
    # Shared schemas are byte-identical in D and the pinned A commit. All A-only
    # modules use a private package and a local import hook; no global app
    # module is swapped, and no source text is rewritten.
    backend = str(ROOT / 'backend')
    if backend not in sys.path:
        sys.path.insert(0, backend)
    for name in ('contracts', 'canonical'):
        path = 'backend/app/schemas/world/' + name + '.py'
        source = (ROOT / path).read_bytes()
        _require(hashlib.sha256(source).hexdigest() == A_FILES[path] and source == read_authority_source(path),
                 'A/D shared schema byte mismatch:' + name)
        module = importlib.import_module('app.schemas.world.' + name)
        _require(Path(module.__file__).resolve() == (ROOT / path).resolve(), 'foreign loaded A contract module')
    contracts = sys.modules['app.schemas.world.contracts']
    if _NAMESPACE + '.units' not in sys.modules:
        package = types.ModuleType(_NAMESPACE)
        package.__path__ = []
        sys.modules[_NAMESPACE] = package
        def pinned_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and name in ('app.schemas.world.v2.work', 'app.schemas.world.v2.contexts'):
                _require(bool(fromlist), 'unsupported whole package import')
                return sys.modules[_NAMESPACE + '.' + name.rsplit('.', 1)[-1]]
            return builtins.__import__(name, globals, locals, fromlist, level)
        try:
            for path, expected_hash in list(A_FILES.items())[2:]:
                source = read_authority_source(path, expected_sha256=expected_hash)
                _require(hashlib.sha256(source).hexdigest() == expected_hash, 'pinned A source byte mismatch:' + path)
                name = Path(path).stem
                module = types.ModuleType(_NAMESPACE + '.' + name)
                module.__file__ = authority_source_reads()[path]['source'] + ':' + A_COMMIT + ':' + path
                module.__package__ = _NAMESPACE
                module.__builtins__ = {**vars(builtins), '__import__': pinned_import}
                sys.modules[module.__name__] = module
                exec(compile(source, module.__file__, 'exec'), module.__dict__)
        except Exception:
            for name in list(sys.modules):
                if name == _NAMESPACE or name.startswith(_NAMESPACE + '.'):
                    del sys.modules[name]
            raise
    return types.SimpleNamespace(contracts=contracts,
        SettlementGroup=sys.modules[_NAMESPACE + '.work'].SettlementGroup,
        preview_point=sys.modules[_NAMESPACE + '.preview'].preview_point,
        preview_over_budget=sys.modules[_NAMESPACE + '.preview'].preview_over_budget,
        validate_unit=sys.modules[_NAMESPACE + '.units'].validate_unit,
        validate_commit_groups=sys.modules[_NAMESPACE + '.units'].validate_commit_groups)


def authority_identity():
    # The default kernel route validates the entire retained bundle before any
    # authority identity may claim it. All code hashes/commit remain unchanged.
    bundle = _verified_snapshot()
    return {'mode': 'offline_pinned_A_preview_point', 'sourceCommit': A_COMMIT,
            'sourceFiles': copy.deepcopy(A_FILES),
            'sourceRetrieval': {'source': 'verified_fixed_commit_bundle', 'snapshotRoot': str(AUTHORITY_SNAPSHOT),
                                'cacheRoot': str(AUTHORITY_CACHE), 'files': copy.deepcopy(_SNAPSHOT_CACHE[2]),
                                'verifiedFiles': len(bundle), 'completeBundleSha256': digest(A_FILES),
                                'gitFallbackPolicy': 'explicit_git_first_5_seconds_then_same_verified_snapshot',
                                'cachedBytesPolicy': 'immutable_full_bundle_bound_to_commit_paths_and_hashes'},
            'partialValidation': 'official SettlementGroup + preview_point + merge + apply',
            'completeValidation': 'official validate_unit after U6',
            'serviceOrDatabaseAccess': False, 'productionIntegration': False}


class OfflinePreview:
    """One fixed pre-point baseline and one fixed metadata/time proposal.

    Every call recomputes the entire stage prefix from that same baseline.
    This avoids applying time or a description twice. This adapter is for a
    single isolated settlement experiment, not multi-unit point scheduling.
    """
    def __init__(self, base_world, binding, *, point=None, group_id=None, actor_ids=None):
        self.base = copy.deepcopy(base_world)
        self.binding = copy.deepcopy(binding)
        self.point = copy.deepcopy(point)
        self.group_id, self.actor_ids = copy.deepcopy(group_id), copy.deepcopy(actor_ids)
        self.group_hash = digest([self.group_id, self.actor_ids])
        self.base_hash, self.point_hash = digest(self.base), digest(self.point)
        self.events, self.prefixes = [], {}
        self.identity = authority_identity()

    def __call__(self, request):
        started = time.perf_counter()
        event = {'mode': self.identity['mode'], 'request': copy.deepcopy(request), 'status': 'started'}
        try:
            _require(self.point is not None, 'offline_preview_missing_registered_point_time')
            _require(isinstance(self.actor_ids, list), 'offline_preview_missing_explicit_actor_ids')
            _require(digest([self.group_id, self.actor_ids]) == self.group_hash, 'offline_preview_group_mutated')
            _require(digest(self.base) == self.base_hash and digest(self.point) == self.point_hash, 'offline_preview_baseline_mutated')
            _require(request['binding'] == self.binding and request['baseWorldHash'] == self.base_hash, 'stale_offline_preview_binding')
            calls = request['completedStages']
            _require(isinstance(calls, list) and 1 <= len(calls) <= 6, 'invalid_stage_prefix')
            _require([c['stage'] for c in calls] == list(STAGES[:len(calls)]) and request['stage'] == calls[-1]['stage'], 'unordered_stage_prefix')
            _require(request['candidateHash'] == digest(calls), 'candidate_prefix_hash_mismatch')
            for index, call in enumerate(calls):
                known = self.prefixes.get(index)
                _require(known is None or known == digest(call), 'frozen_stage_candidate_rewrite')
            kernel = _load_kernel()
            contracts = kernel.contracts
            state = contracts.WorldState.model_validate(self.base)
            _require(set(self.point) == {'worldId', 'id', 'sequence', 'kind', 'previousPointId', 'roundId', 'advanceId', 'trigger', 'linkedFromPointId', 'timeAdvance'}, 'registered_point_metadata_required')
            _require(self.point['worldId'] == state.worldId and self.point['id'] == self.binding['pointId'], 'offline_point_identity_mismatch')
            entities = {**self.base['locations'], **self.base['items'], **self.base['characters']}
            occupied = set(entities)
            for entity in entities.values():
                occupied.update(entity.get('tasks', {}))
                for field in ('appearanceChanges', 'personalityChanges'):
                    occupied.update(record['id'] for record in entity.get(field, []))
            created, merged = set(), {}
            wire = {"groupId": self.group_id, "actorIds": self.actor_ids,
                    **{field: {} for field in _WIRE_FIELDS.values()},
                    "taskCoverageIds": sorted(state.characters) if len(calls) >= 3 else [],
                    "personalityCoverageIds": []}
            for call in calls:
                field = _FIELDS[call['stage']]
                for owner, delta in call['changes'].items():
                    _require(owner in entities and set(delta) == {'entityId', field} and delta['entityId'] == owner, 'wrong_stage_or_entity_delta')
                    target = merged.setdefault(owner, {'entityId': owner})
                    _require(field not in target, 'duplicate_field_no_last_write_wins')
                    target[field] = copy.deepcopy(delta[field])
                    wire[_WIRE_FIELDS[call['stage']]][owner] = copy.deepcopy(delta[field])
                    if field in ('appearanceChanges', 'personalityChanges', 'subtasksAdded'):
                        for item in delta[field]:
                            _require(item['id'] not in occupied and item['id'] not in created, 'new_record_identity_collision')
                            created.add(item['id'])
                            if field == 'subtasksAdded':
                                _require(item['status'] == 'pending', 'new_task_must_remain_pending')
            if len(calls) >= 5 and wire['tasksAchieved']:
                wire['personalityCoverageIds'] = sorted(state.characters)
            unit = kernel.SettlementGroup.model_validate(wire)
            if len(calls) == 6:
                violations = kernel.validate_unit(unit, frozenset(state.characters))
                _require(not violations, 'A_complete_unit_rejected:' + str(violations))
            point = contracts.TimelinePoint.model_validate({**self.point, 'entityDeltas': {}})
            request_bytes = len(json.dumps({'point': self.point, 'settlementGroups': [wire]}, ensure_ascii=False).encode())
            _require(kernel.preview_over_budget(request_bytes) is None, 'A_preview_request_budget')
            projection = kernel.preview_point(state, point, [unit])
            response_bytes = len(json.dumps(projection, ensure_ascii=False).encode())
            _require(kernel.preview_over_budget(request_bytes, response_bytes) is None, 'A_preview_response_budget')
            world = projection['workingState']
            # A normalizes optional fields. Verify the entire initial model is
            # unchanged, then preserve its caller representation byte-for-byte;
            # this does not change any initial semantic field.
            _require(world['initial'] == state.initial.model_dump(mode='json'), 'A_preview_changed_initial_semantics')
            world['initial'] = copy.deepcopy(self.base['initial'])
            event.update(requestBytes=request_bytes, responseBytes=response_bytes,
                         officialWorkingStateDigest=projection['workingStateDigest'],
                         pointProjectionDigest=projection['pointProjectionDigest'],
                         completeUnitValidated=len(calls) == 6)
            for index, call in enumerate(calls):
                self.prefixes[index] = digest(call)
            event.update(status='result', workingStateHash=digest(world))
            return result({**{key: copy.deepcopy(request[key]) for key in ('binding', 'baseWorldHash', 'candidateHash', 'stage')},
                           'world': world, 'authority': copy.deepcopy(self.identity), 'committed': False})
        except Exception as exc:
            event.update(status='incomplete', error={'type': type(exc).__name__, 'message': str(exc)})
            return incomplete('offline_A_preview:' + str(exc))
        finally:
            event['elapsedMs'] = (time.perf_counter() - started) * 1000
            self.events.append(event)


def offline_preview(base_world, binding, *, point=None, group_id=None, actor_ids=None):
    return OfflinePreview(base_world, binding, point=point, group_id=group_id, actor_ids=actor_ids)
