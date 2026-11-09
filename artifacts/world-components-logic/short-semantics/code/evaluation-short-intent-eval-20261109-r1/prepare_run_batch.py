"""Read-only preparation of D batches; never import or execute a model stack.

--write-new publishes a new preparation snapshot without replacing evidence.
--check validates one snapshot and reports unresolved execution prerequisites.
Neither command authorizes execution or invokes runtime_smoke.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from typing import Any

from lab import guard_case, canonical_bytes, load_jsonl

ROOT = Path(__file__).resolve().parents[2]
BASE = 'experiments/world-components-logic/'
LOCAL = '.local/world-components-logic/'
ARTIFACTS = 'artifacts/world-components-logic/'
DEFAULT = ARTIFACTS + 'l3-3-run-preparation.json'
HISTORY = ARTIFACTS + 'l3-1-environment.json'
REGISTRY = ARTIFACTS + 'l2-model-sources-20261029.json'
LEDGER = ARTIFACTS + 'run-manifest-ledger-v4.proposal.json'
LOCK = BASE + 'requirements-probe-macos-arm64-py311.lock.txt'
SOURCE_FILES = (HISTORY, REGISTRY, LEDGER, LOCK, BASE + 'runtime_smoke.py', BASE + 'lab.py',
                BASE + 'prepare_run_batch.py',
                'design/world-engine-reports/components-logic/run-manifest.md',
                'design/world-engine-reports/components-logic/model-selection.md',
                'design/world-engine-reports/components-logic/evaluation-plan.md')
M02_FILES = ('README.md', 'config.json', 'tokenizer_config.json',
             'special_tokens_map.json', 'spiece.model', 'model.safetensors')
BATCH_IDS = ('nonbusiness_load_diagnostic', 'development_diagnostic', 'm01_head_training')
TRAIN_FIELDS = ('sourceGroups', 'labels', 'labelReviewEvidence', 'isolationEvidence',
                'optimizer', 'learningRate', 'batchSize', 'maxSteps', 'earlyStopping',
                'seed', 'losses', 'backbonePolicy', 'maxWallSeconds', 'maxResidentMiB')


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def sha256_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def owned_path(root: Path, relative: str, prefix: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not relative.startswith(prefix):
        raise ValueError(f'outside the registered D path: {relative}')
    result = root / path
    # Allow the venv executable's normal symlink only for stat observations,
    # never for this helper's content/hash reads.
    if not result.resolve().is_relative_to(root.resolve() / prefix.rstrip('/')):
        raise ValueError(f'redirected D path: {relative}')
    return result


def read_json(root: Path, relative: str) -> dict[str, Any]:
    prefix = next((p for p in (BASE, ARTIFACTS, LOCAL,
                              'design/world-engine-reports/components-logic/') if relative.startswith(p)), None)
    if prefix is None:
        raise ValueError(f'not a D file: {relative}')
    path = owned_path(root, relative, prefix)
    if path.stat().st_size > 4_000_000:
        raise ValueError(f'not a small configuration: {relative}')
    return json.loads(path.read_text(encoding='utf-8'))


def package_inventory(venv: Path, python_version: str) -> dict[str, str]:
    """Inspect only installed METADATA text; never import installed packages."""
    site = venv / 'lib' / ('python' + '.'.join(python_version.split('.')[:2])) / 'site-packages'
    packages = {}
    for path in sorted(site.glob('*.dist-info/METADATA')):
        if not path.resolve().is_relative_to(venv.resolve()):
            raise ValueError('redirected package metadata')
        fields = {}
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                if not line.strip():
                    break
                key, _, value = line.partition(':')
                if key in ('Name', 'Version'):
                    fields[key] = value.strip()
        if 'Name' in fields and 'Version' in fields:
            name = re.sub(r'[-_.]+', '-', fields['Name']).lower()
            if name in packages:
                raise ValueError(f'duplicate installed metadata: {name}')
            packages[name] = fields['Version']
    return packages


def observe_environment(root: Path) -> dict[str, Any]:
    history = read_json(root, HISTORY)
    venv_relative = history['venvRelativePath']
    venv = owned_path(root, venv_relative, LOCAL)
    cfg = venv / 'pyvenv.cfg'
    values = {}
    if cfg.is_file():
        for line in cfg.read_text(encoding='utf-8').splitlines():
            key, _, value = line.partition('=')
            values[key.strip()] = value.strip()
    executable = venv / 'bin/python'
    installed = package_inventory(venv, values.get('version', '3.11')) if cfg.exists() else {}
    locked = {re.sub(r'[-_.]+', '-', p['name']).lower(): p['version'] for p in history['packages']}
    return {
        'platform': platform.platform(), 'machine': platform.machine(),
        'checkerPythonVersion': platform.python_version(),
        'venvRelativePath': venv_relative, 'venvConfigExists': cfg.is_file(),
        'venvConfigSha256': sha256_file(cfg) if cfg.is_file() else None,
        'venvPythonVersion': values.get('version'),
        'venvExecutableRelativePath': executable.relative_to(root).as_posix(),
        'venvExecutableExists': executable.is_file(),
        'venvExecutablePermission': os.access(executable, os.X_OK),
        'venvExecutableSymlinkTarget': os.readlink(executable) if executable.is_symlink() else None,
        'systemSitePackages': values.get('include-system-site-packages'),
        'lockFile': LOCK, 'lockSha256': sha256_file(root / LOCK),
        'lockMatchesHistoricalIdentity': sha256_file(root / LOCK) == history['lockSha256'],
        'historicallyRegisteredPackageCount': len(locked),
        'registeredInstalledVersions': {name: installed.get(name) for name in locked},
        'registeredVersionsMatch': all(installed.get(name) == version for name, version in locked.items()),
        'historicalPlatformMatches': platform.platform() == history['platform'] and platform.machine() == history['machine'],
        'hostAttestation': None,
        'hostIdentityScope': 'Observed original D workspace path, platform and existing isolated files; no unique physical-host attestation or runtime import test.',
        'environmentRebuilt': False, 'dependenciesImported': False,
    }


def observe_m02(root: Path, *, hash_weights: bool = True) -> dict[str, Any]:
    registry = read_json(root, REGISTRY)
    model = next(m for m in registry['models'] if m['id'] == 'IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese')
    if not re.fullmatch(r'[a-f0-9]{40}', model['revision']):
        raise ValueError('invalid M02 revision')
    relative = LOCAL + 'models/M02/' + model['revision']
    directory = owned_path(root, relative, LOCAL)
    payload = directory / 'payload-manifest.json'
    inventory = json.loads(payload.read_text(encoding='utf-8')) if payload.is_file() else None
    expected = {f['path']: f for f in model['files']}
    files = []
    for name in M02_FILES:
        path = owned_path(root, relative + '/' + name, LOCAL)
        spec = expected[name]
        registered_sha = spec.get('lfs_sha256') or spec.get('sha256_of_fetched_bytes')
        exists = path.is_file()
        hashed = exists and (hash_weights or name != 'model.safetensors')
        actual_sha = sha256_file(path) if hashed else None
        size = path.stat().st_size if exists else None
        files.append({'path': name, 'expectedBytes': spec['size_bytes'], 'observedBytes': size,
                      'registeredSha256': registered_sha, 'observedSha256': actual_sha,
                      'status': 'missing' if not exists else 'not_rehashed' if not hashed else
                      'verified' if actual_sha == registered_sha and size == spec['size_bytes'] else 'mismatch'})
    payload_matches = bool(inventory and inventory.get('modelId') == model['id']
                           and inventory.get('revision') == model['revision']
                           and inventory.get('sourceRegistrySha256') == sha256_file(root / REGISTRY)
                           and len(inventory.get('files', [])) == 6
                           and {f['path']: (f['bytes'], f['sha256']) for f in inventory['files']} ==
                           {f['path']: (f['expectedBytes'], f['registeredSha256']) for f in files})
    return {'modelId': model['id'], 'revision': model['revision'], 'directory': relative,
            'payloadManifestExists': payload.is_file(),
            'payloadManifestSha256': sha256_file(payload) if payload.is_file() else None,
            'payloadInventoryMatchesRegistry': payload_matches, 'files': files,
            'allSixFilesFullyRehashedAndVerified': payload_matches and all(f['status'] == 'verified' for f in files),
            'modelLoaded': False, 'tokenizerLoaded': False, 'modelExecutionPerformed': False}


def bind_development(root: Path, relative: str | None, case_ids: list[str]) -> dict[str, Any]:
    """Bind only an explicitly selected dev-only JSONL; no sealed file reads."""
    unbound = {'path': None, 'sha256': None, 'caseIds': [], 'split': 'development',
               'sourceManifestPath': None, 'sourceManifestSha256': None, 'selectedCases': [],
               'inputReviewEvidence': None, 'sourceIsolationEvidence': None,
               'status': 'awaiting_versioned_development_inputs'}
    if relative is None:
        if case_ids:
            raise ValueError('--case-id requires --development-inputs')
        return unbound
    path = owned_path(root, relative, BASE + 'data/round1-inputs/')
    if path.name not in ('dev-inputs.jsonl', 'development-inputs.jsonl'):
        raise ValueError('bind the dev-only input file; manifests/mixed/sealed inputs are not accepted')
    if path.stat().st_size > 4_000_000:
        raise ValueError('development diagnostic input is too large for preparation')
    rows = load_jsonl(path)
    ids = [row['caseId'] for row in rows]
    if not rows or len(set(ids)) != len(ids) or any(row.get('split') != 'development' for row in rows):
        raise ValueError('development file must contain unique, development-only cases')
    if not case_ids or len(set(case_ids)) != len(case_ids) or not set(case_ids) <= set(ids):
        raise ValueError('explicit unique --case-id selections are required; no automatic all-case exposure')
    manifest_relative = BASE + 'data/round1-inputs/input-manifest.json'
    manifest = read_json(root, manifest_relative)
    if manifest['files'].get(path.name) != sha256_file(path):
        raise ValueError('development inputs do not match the authored input manifest')
    indexed = {r['caseId']: r for r in rows}
    selected = []
    for cid in case_ids:
        row = indexed[cid]
        guard = guard_case(row)
        if not guard['shouldCall']:
            raise ValueError(f'selected diagnostic input is a guard-only case: {cid}')
        selected.append({'caseId': cid, 'task': row['task'],
                         'caseSha256': hashlib.sha256(canonical_bytes(row)).hexdigest(),
                         'guard': guard})
    unbound.update(path=relative, sha256=sha256_file(path), caseIds=case_ids,
                   sourceManifestPath=manifest_relative, sourceManifestSha256=sha256_file(root / manifest_relative),
                   selectedCases=selected,
                   status='identity_bound_review_and_freeze_pending')
    return unbound


def batches(binding: dict[str, Any]) -> list[dict[str, Any]]:
    common = {'executionAuthorized': False, 'authorizationEvidence': None,
              'modelExecutionPerformed': False, 'owner': None, 'resourceWindow': None,
              'configurationFrozen': False, 'formalScreeningAllowed': False}
    smoke = dict(common, batchId=BATCH_IDS[0], modelIds=['M02'],
                 scope='nonbusiness_load_and_synthetic_generation_only', businessCaseIds=[],
                 requiresAll90Groups=False, inputReviewRequired=False,
                 existingEntrypoint=BASE + 'runtime_smoke.py',
                 newRunId=None, existingEvidenceMayBeOverwritten=False,
                 configuration={'device': 'cpu', 'threads': 1, 'concurrency': 1,
                                'prompt': '运行检查：请写出“模型已载入”。', 'maxNewTokens': 12,
                                'doSample': False, 'seed': 42, 'attempts': 1,
                                'softGenerationLimitSeconds': 3,
                                'processWallLimitSeconds': None, 'maxResidentMiB': None,
                                'localFilesOnly': True, 'tokenizerExtraIds': 0,
                                'resizeEmbeddings': False},
                 performanceClaimAllowed=False)
    dev = dict(common, batchId=BATCH_IDS[1], modelIds=['M02'],
               scope='development_components_with_program_fixtures_only',
               tasks=['D02.direct-act-skip-and-body', 'D03.direct-targets', 'D04.reaction', 'D05.direct-joint-results'],
               arm='M02_direct_generation_feasibility_probe_not_M01_M02_collaboration',
               requiresAll90Groups=False, sealedCandidatesAllowed=False,
               inputSelection=binding, inputReviewRequired=True,
               trainedM01Checkpoint=None, trainedM01CheckpointSha256=None,
               fixedProgramFixtureIdentity={'inputManifestSha256': binding['sourceManifestSha256'],
                                            'kind': 'authored_program_fixtures_not_service_receipts'},
               projectionAdapterIdentity={'function': 'lab.build_model_input',
                                          'file': BASE+'lab.py',
                                          'runtimeTokenPackingImplemented': False},
               promptAndDecoderConfig={
                   'status': 'draft_not_frozen', 'inputSerialization': 'complete canonical JSON from lab.build_model_input',
                   'instructions': {
                       'D02': '结合完整世界、当前人物的任务和个性判断行动；pending输入须重新判断可行性，consumed/expired不重复消费。只输出严格JSON {"kind":"act","text":"行动尝试"} 或 {"kind":"skip"}；不宣布结果成功。',
                       'D03': '分析已冻结源行动对完整人物名册的牵连，包括已行动人物。只输出严格JSON {"targets":[{"targetId":"登记人物ID"}]}，允许空集。不得给出骰点、准入或未来反应。',
                       'D04': '基于全部已冻结威胁、实际判定、世界、任务和个性生成当前获准人物的一次反应尝试。只输出非空正文，不改写冻结动作，不保证成功，不自行分配目标或骰点。',
                       'D05': '对已闭合全组动作和全部实际判定统一推导自洽后果，再输出严格JSON：每个组成员ID对应一段结果文本。键集合须恰好等于memberIds；保留失败、未准入和已行动关系，骰点不是命中或胜负规则。',
                   },
                   'decoder': 'lab.decode_output', 'doSample': False, 'seed': 42,
                   'maxInputTokens': 512, 'encodedLengthMeasured': False,
                   'maxNewTokensByTask': {'D02': 128, 'D03': 96, 'D04': 128, 'D05': 256},
                   'truncationAllowed': False,
                   'overflowPolicy': 'stop_and_register_new_complete_coverage_packing_arm',
                   'outputAtTokenLimitPolicy': 'incomplete_attempt_not_success',
               },
               plannedAttemptsPerCase=5,
               runtimeRunnerIdentity=None, tokenCoverageVerified=False,
               inputCoveragePolicy='All required original facts and frozen identities; stageCut projection; no gold/future facts, no silent truncation.',
               resourceBudget={'maxWallSeconds': 60, 'maxResidentMiB': 2048,
                               'status': 'proposed_not_authorized', 'enforcementImplemented': False},
               fullRequestClaimAllowed=False, baselineStatus='baseline_missing')
    training = dict(common, batchId=BATCH_IDS[2], modelIds=['M01'],
                    scope='independent_new_training_protocol_only',
                    targetHeads=['D02.act-skip', 'D03.relation-score'],
                    first90TrainingQuota=0, evaluationGroupsUsedForTraining=0,
                    dataPath=None, dataSha256=None, sourceKind='independent_new_training_groups',
                    protocol={field: None for field in TRAIN_FIELDS},
                    protocolDraft={
                        'status': 'proposed_not_frozen_not_authorized',
                        'dataPlan': {'newGroupsPerHead': 40, 'trainGroupsPerHead': 32,
                                     'validationGroupsPerHead': 8,
                                     'sourceGroupsBuilt': 0, 'groupSplitSeed': 42,
                                     'sameOriginAndCandidatePairsStayInOneSplit': True,
                                     'sourcePolicy': 'New D-only independent training sources; exclude B/C protected material, old42 and all round1 groups/derivatives.'},
                        'labelPlan': 'Human-reviewed D02 act/skip and D03 source-candidate relation labels, with uncertain/disagreement retained; no teacher self-labeling.',
                        'optimizer': 'AdamW', 'learningRate': 0.0002, 'batchSize': 16,
                        'maxSteps': 200, 'validationEverySteps': 20,
                        'earlyStopping': {'metric': 'per-head validation macro-F1', 'patienceChecks': 3,
                                          'keepBestCheckpoint': True},
                        'seed': 42, 'backbonePolicy': 'frozen_encoder_train_two_heads_only_first_probe',
                        'losses': {'D02': 'binary_cross_entropy', 'D03': 'binary_cross_entropy'},
                        'device': 'cpu', 'threads': 1, 'concurrency': 1,
                        'maxWallSeconds': 120, 'maxResidentMiB': 2048,
                        'stopOn': ['resource_cap', 'nonfinite_loss', 'invalid_or_unreviewed_batch', 'cancel'],
                        'resourceCapEnforcement': 'runner_not_implemented',
                        'qualityPassPredicted': False,
                    },
                    trainingRunnerIdentity=None, outputCheckpointSha256=None,
                    randomHeadSemanticComparisonAllowed=False,
                    subsequentInferenceRequiresNewBatch=True)
    return [smoke, dev, training]


def build_preparation(root: Path = ROOT, *, development_inputs: str | None = None,
                      case_ids: list[str] | None = None, hash_weights: bool = True) -> dict[str, Any]:
    ledger = read_json(root, LEDGER)
    registry = read_json(root, REGISTRY)
    try:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        head = None
    binding = bind_development(root, development_inputs, case_ids or [])
    return {
        'schema': 'jity-d-run-preparation-v1', 'preparedOn': '2026-11-01', 'sourceHead': head,
        'scope': 'static_preparation_only_not_an_execution_manifest_or_service_protocol',
        'executionAuthorized': False, 'modelExecutionPerformed': False, 'networkAccessed': False,
        'sources': [{'path': path, 'sha256': sha256_file(root / path)} for path in SOURCE_FILES],
        'environmentObservation': observe_environment(root), 'm02Observation': observe_m02(root, hash_weights=hash_weights),
        'm01': {'repo': registry['models'][0]['id'], 'revision': registry['models'][0]['revision'],
                'businessHeadStatus': 'untrained', 'trainedCheckpoint': None,
                'trainedCheckpointSha256': None, 'businessComparisonAllowed': False},
        'performance': {'fullRequestTargetMs': 500, 'localEngineeringBudgetMs': 50,
                        'referenceBudgets': {s['id']: {'subtotalMs': s['subtotalMs'], 'waits': s['waits']}
                                             for s in ledger['scenarios']},
                        'timingUnit': ledger['timingUnit'], 'status': 'latency_unverified',
                        'diagnosticMayObserveBudgetFailure': True, 'priorMeasuredPassRequired': False,
                        'allAttemptsIncludingFailuresRecorded': True,
                        'futureDynamicCounts': None, 'dynamicCountsMustNotBeForced': True,
                        'waitsRemainInFullRequest': True},
        'integration': {'programApiMapping': 'unexpanded', 'g03': 'blocked_contract_g03',
                        'browserOrProductionClaimAllowed': False},
        'batches': batches(binding),
        'executionDispatchImplemented': False,
    }


def execution_blockers(batch: dict[str, Any], preparation: dict[str, Any]) -> list[str]:
    """Report prerequisites; this module provides no execution transition."""
    blockers = []
    for key in ('executionAuthorized', 'authorizationEvidence', 'owner', 'resourceWindow', 'configurationFrozen'):
        if not batch.get(key):
            blockers.append(key)
    env = preparation['environmentObservation']
    if not (env['venvExecutableExists'] and env['venvExecutablePermission'] and
            env['lockMatchesHistoricalIdentity'] and env['registeredVersionsMatch']):
        blockers.append('isolated_environment_identity')
    if 'M02' in batch['modelIds'] and not preparation['m02Observation']['allSixFilesFullyRehashedAndVerified']:
        blockers.append('M02_payload_verification')
    if batch['batchId'] == BATCH_IDS[0]:
        for key in ('newRunId',):
            if not batch.get(key):
                blockers.append(key)
        for key in ('processWallLimitSeconds', 'maxResidentMiB'):
            if batch['configuration'].get(key) is None:
                blockers.append(key)
    if batch['batchId'] == BATCH_IDS[1]:
        selection = batch['inputSelection']
        for key in ('path', 'sha256', 'caseIds', 'inputReviewEvidence', 'sourceIsolationEvidence'):
            if not selection.get(key):
                blockers.append('inputSelection.' + key)
        for key in ('fixedProgramFixtureIdentity', 'projectionAdapterIdentity', 'promptAndDecoderConfig', 'plannedAttemptsPerCase', 'runtimeRunnerIdentity', 'tokenCoverageVerified'):
            if not batch.get(key):
                blockers.append(key)
        for key, value in batch['resourceBudget'].items():
            if value is None:
                blockers.append('resourceBudget.' + key)
        if not batch['resourceBudget'].get('enforcementImplemented'):
            blockers.append('resourceBudget.enforcementImplemented')
        if 'M01' in batch['modelIds'] and not (batch.get('trainedM01Checkpoint') and batch.get('trainedM01CheckpointSha256')):
            blockers.append('trained_M01_business_head')
    if batch['batchId'] == BATCH_IDS[2]:
        blockers.append('M01_base_payload_not_reverified')
        for key in ('dataPath', 'dataSha256', 'trainingRunnerIdentity'):
            if not batch.get(key):
                blockers.append(key)
        blockers.extend('protocol.' + key for key in TRAIN_FIELDS if batch['protocol'].get(key) is None)
    return blockers


def validate(preparation: dict[str, Any], root: Path = ROOT, *, recheck_files: bool = True) -> list[str]:
    errors = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    need(preparation.get('schema') == 'jity-d-run-preparation-v1', 'wrong preparation schema')
    for field in ('executionAuthorized', 'modelExecutionPerformed', 'networkAccessed', 'executionDispatchImplemented'):
        need(preparation.get(field) is False, f'{field} must remain false')
    need(preparation['performance'].get('fullRequestTargetMs') == 500, '500 ms target cannot change')
    need(preparation['performance'].get('status') == 'latency_unverified', 'static preparation cannot claim measured latency')
    need(preparation['performance'].get('futureDynamicCounts') is None, 'unknown actual dynamic counts must remain null')
    need(preparation['performance'].get('priorMeasuredPassRequired') is False
         and preparation['performance'].get('diagnosticMayObserveBudgetFailure') is True,
         'first diagnostic cannot require an existing latency pass')
    need(preparation['performance'].get('waitsRemainInFullRequest') is True, 'ready waits belong in full request')
    need(preparation['integration'] == {'programApiMapping': 'unexpanded', 'g03': 'blocked_contract_g03',
                                       'browserOrProductionClaimAllowed': False}, 'API/G03 integration remains unresolved')
    need(preparation['m01'].get('businessHeadStatus') == 'untrained'
         and preparation['m01'].get('businessComparisonAllowed') is False, 'M01 random/untrained head cannot enter comparison')
    need([batch['batchId'] for batch in preparation['batches']] == list(BATCH_IDS), 'register three distinct batches')
    for batch in preparation['batches']:
        for field in ('executionAuthorized', 'modelExecutionPerformed', 'configurationFrozen', 'formalScreeningAllowed'):
            need(batch.get(field) is False, f"{batch['batchId']}: {field} must remain false")
        need(batch.get('authorizationEvidence') is None and batch.get('owner') is None
             and batch.get('resourceWindow') is None, f"{batch['batchId']}: do not invent authorization/owner/window evidence")
        need(bool(execution_blockers(batch, preparation)), f"{batch['batchId']}: preparation cannot release execution")
        if batch['batchId'] == BATCH_IDS[0]:
            need(batch.get('businessCaseIds') == [] and batch.get('requiresAll90Groups') is False
                 and batch.get('inputReviewRequired') is False, 'smoke must remain nonbusiness and independent of all90')
            need(batch.get('performanceClaimAllowed') is False and batch.get('existingEvidenceMayBeOverwritten') is False,
                 'smoke cannot claim performance or replace historical records')
        if batch['batchId'] == BATCH_IDS[1]:
            selection = batch['inputSelection']
            need(batch.get('sealedCandidatesAllowed') is False and batch.get('fullRequestClaimAllowed') is False,
                 'development diagnostics cannot consume sealed cases or sign full requests')
            need(selection.get('split') == 'development' and selection.get('inputReviewEvidence') is None
                 and selection.get('sourceIsolationEvidence') is None, 'new input review/isolation remains unverified')
            need(batch.get('trainedM01Checkpoint') is None and batch.get('trainedM01CheckpointSha256') is None,
                 'no trained M01 head identity has been supplied')
            config = batch['promptAndDecoderConfig']
            need(config.get('status') == 'draft_not_frozen' and config.get('truncationAllowed') is False
                 and config.get('encodedLengthMeasured') is False and config.get('doSample') is False
                 and set(config.get('instructions', {})) == {'D02', 'D03', 'D04', 'D05'},
                 'draft prompts must preserve all input without claiming token coverage')
            need(batch.get('tokenCoverageVerified') is False and batch.get('runtimeRunnerIdentity') is None
                 and batch['resourceBudget'].get('enforcementImplemented') is False,
                 'runtime token coverage, runner and resource enforcement remain unimplemented')
            if selection['path'] is None:
                need(selection.get('sha256') is None and selection.get('caseIds') == [], 'unbound input must not have an invented hash/case list')
            elif recheck_files:
                bound = bind_development(root, selection['path'], selection['caseIds'])
                need(bound == selection, 'development input identity changed; create a new preparation snapshot')
        if batch['batchId'] == BATCH_IDS[2]:
            need(batch.get('first90TrainingQuota') == 0 and batch.get('evaluationGroupsUsedForTraining') == 0,
                 'the 90 evaluation groups have zero training quota')
            need(batch.get('sourceKind') == 'independent_new_training_groups'
                 and batch.get('dataPath') is None and batch.get('dataSha256') is None,
                 'training data must be independently registered, not evaluation inputs')
            need(set(batch['protocol']) == set(TRAIN_FIELDS) and all(value is None for value in batch['protocol'].values()),
                 'unknown training configuration must remain unfrozen/null')
            need(batch.get('randomHeadSemanticComparisonAllowed') is False
                 and batch.get('subsequentInferenceRequiresNewBatch') is True, 'training and subsequent inference require separate batches')
    if recheck_files:
        need([source['path'] for source in preparation['sources']] == list(SOURCE_FILES), 'registered preparation source inventory changed')
        for source in preparation['sources']:
            if source['path'] in SOURCE_FILES:
                need(sha256_file(owned_path(root, source['path'], source['path'].split('/')[0] + '/')) == source['sha256'],
                     'source identity changed: ' + source['path'])
        need(observe_environment(root) == preparation['environmentObservation'], 'environment observation changed; register a new snapshot')
        rehash = next(f for f in preparation['m02Observation']['files'] if f['path'] == 'model.safetensors')['observedSha256'] is not None
        need(observe_m02(root, hash_weights=rehash) == preparation['m02Observation'], 'M02 observation changed; register a new snapshot')
        ledger = read_json(root, LEDGER)
        need(preparation['performance']['referenceBudgets'] == {s['id']: {'subtotalMs': s['subtotalMs'], 'waits': s['waits']}
                                                               for s in ledger['scenarios']}, 'reference budgets/waits differ from v4 ledger')
    return errors


def write_new(path: Path, content: bytes) -> None:
    """Publish complete bytes via an exclusive link; never overwrite evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(content)
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check', nargs='?', const=DEFAULT, metavar='SNAPSHOT')
    modes.add_argument('--write-new', nargs='?', const=DEFAULT, metavar='NEW_SNAPSHOT')
    parser.add_argument('--development-inputs', help='explicit dev-only round1-inputs JSONL to bind in a NEW snapshot')
    parser.add_argument('--case-id', action='append', default=[], help='explicit development case selection; repeatable')
    parser.add_argument('--skip-weight-hash', action='store_true', help='record the 310 MB weight as not_rehashed, never verified')
    args = parser.parse_args()
    try:
        relative = args.check or args.write_new
        path = owned_path(ROOT, relative, ARTIFACTS)
        if args.check:
            if args.skip_weight_hash or args.development_inputs or args.case_id:
                raise ValueError('check uses the recorded identity; bind changes with --write-new NEW_SNAPSHOT')
            preparation = read_json(ROOT, relative)
        else:
            if path.exists():
                raise FileExistsError('preparation already exists; preserve it and choose a new snapshot filename')
            preparation = build_preparation(development_inputs=args.development_inputs, case_ids=args.case_id,
                                             hash_weights=not args.skip_weight_hash)
        errors = validate(preparation)
        if errors:
            for error in errors:
                print('FAIL: ' + error, file=sys.stderr)
            return 1
        if args.write_new:
            write_new(path, canonical(preparation))
        print('PASS: static preparation identity and guards; no model execution or authorization.')
        for batch in preparation['batches']:
            print(batch['batchId'] + ': BLOCKED: ' + ', '.join(execution_blockers(batch, preparation)))
        return 0
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
