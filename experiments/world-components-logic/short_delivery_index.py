"""Read-only delivery indexing: no model import, inference, staging or deletion.

Use --output only after final browser evidence exists. Existing inventories are
never overwritten. Live files get a point-in-time hash, not a finality claim.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parents[2]
WEIGHTS = ('.pt', '.pth', '.bin', '.safetensors', '.onnx', '.onnx_data', '.gguf')
RAW = ('.record.json', '.record.json.gz', '.journal.jsonl', '.journal.jsonl.gz',
       '.webgpu.jsonl', '.webgpu.jsonl.gz', '.process.log', '.stderr.log',
       '.process.log.gz', '.stderr.log.gz',
       '.export-record.json', '.export-record.json.gz')
PLAN_SUFFIXES = ('.plan.json', '.export-plan.json')
RECORD_SUFFIXES = ('.record.json', '.export-record.json')
NOT_FINAL = {'running', 'started', 'prepared', 'pending', 'executing'}
NO_EXECUTION = {'superseded_before_execution', 'cancelled_before_execution'}
MAX_METADATA_BYTES = 8 * 1024 * 1024


def is_record(path):
    return str(path).removesuffix('.gz').endswith(RECORD_SUFFIXES)


def record_for_plan(path):
    path = Path(path)
    if path.name.endswith('.export-plan.json'):
        return path.with_name(path.name.removesuffix('.export-plan.json') + '.export-record.json')
    return path.with_name(path.name.removesuffix('.plan.json') + '.record.json')


def resolve_reference(path, root):
    path = Path(path)
    return (path if path.is_absolute() else root / path).resolve()


def cloud_placeholder(path):
    # macOS UF_DATALESS: stat is local; reading these bytes can hydrate iCloud.
    return bool(getattr(Path(path).stat(), 'st_flags', 0) & 0x40000000)


def category(path):
    name = Path(path).name
    if name.endswith(WEIGHTS):
        return 'model_weights_local_only'
    if name.endswith(RAW) or name.startswith('browser-tokenizer-probe-'):
        return 'raw_evidence_local_only'
    if name.endswith(PLAN_SUFFIXES):
        return 'frozen_plan'
    if 'quarantine' in str(path) or 'correction' in name or 'superseded' in name:
        return 'disposition_evidence'
    if 'summary' in name and name.endswith('.json'):
        return 'summary'
    if name == 'provider.json' or name.endswith('.provider.json'):
        return 'provider_identity'
    if 'manifest' in name or 'archive' in name or 'inventory' in name or name.endswith('.webgpu-model.json'):
        return 'identity_index'
    if name.endswith('.log'):
        return 'preparation_or_engineering_log'
    if any(part in Path(path).parts for part in ('snapshots', 'eval-snapshots', 'code')):
        return 'source_snapshot'
    return 'small_supporting_material'


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def file_entry(path, root, *, hash_weights=False, hash_raw=False):
    path = Path(path).resolve()
    row = {'path': str(path), 'type': category(path), 'exists': path.is_file()}
    if not row['exists']:
        return row
    row['relativePath'] = str(path.relative_to(root)) if path.is_relative_to(root) else None
    before = path.stat()
    row.update(bytes=before.st_size, observedMtimeNs=before.st_mtime_ns, cloudPlaceholder=cloud_placeholder(path))
    if row['cloudPlaceholder']:
        row.update(sha256=None, verification='cloud_placeholder_not_hydrated')
    elif row['type'] == 'model_weights_local_only' and not hash_weights:
        row.update(sha256=None, verification='size_only_model_bytes_not_read')
    elif row['type'] == 'raw_evidence_local_only' and not hash_raw:
        row.update(sha256=None, verification='size_only_raw_bytes_not_rehashed')
    else:
        row['sha256'] = sha256(path)
        after = path.stat()
        row['stableDuringRead'] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        row['verification'] = 'streamed_local_bytes' if row['stableDuringRead'] else 'changed_during_read'
    return row


def git_state(root, paths):
    relative = [str(p.relative_to(root)) for p in paths if p.is_relative_to(root)]
    if not relative:
        return {}, {}
    tracked = set()
    for offset in range(0, len(relative), 200):
        tracked.update(subprocess.run(['git', 'ls-files', '-z', '--', *relative[offset:offset + 200]], cwd=root,
            capture_output=True, check=True).stdout.decode().split('\0'))
    ignored = subprocess.run(['git', 'check-ignore', '--no-index', '-z', '--stdin'], cwd=root,
        input=('\0'.join(relative) + '\0').encode(), capture_output=True)
    if ignored.returncode not in (0, 1):
        raise RuntimeError('git_ignore_check_failed:' + ignored.stderr.decode())
    return tracked - {''}, set(ignored.stdout.decode().split('\0')) - {''}


def compact_record(value):
    keys = ('runId', 'schema', 'status', 'formalEvaluationAllowed', 'semanticQualityApproved',
            'fullRequestMeasured', 'planSha256', 'reason', 'modelCalls', 'trainingSteps', 'completion')
    answer = {key: value[key] for key in keys if key in value}
    attempts = value.get('attempts', [])
    answer['attempts'] = [{key: row[key] for key in ('arm', 'caseId', 'status', 'stopReason',
        'error', 'wallMs', 'elapsedThroughResultMs') if key in row} for row in attempts]
    answer['slotsByStatus'] = dict(Counter(row.get('status', 'unspecified')
        for row in value.get('attemptSlots', []) if isinstance(row, dict)))
    return answer


def manifest_assets(path, value):
    directory = value.get('directory')
    files = value.get('files')
    file_rows = files if isinstance(files, list) else []
    if isinstance(directory, str) and isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and isinstance(item.get('path'), str):
                yield Path(directory) / item['path'], item.get('sha256', item.get('observedSha256'))
    checkpoint = value.get('checkpoint')
    if isinstance(checkpoint, dict) and isinstance(checkpoint.get('path'), str):
        yield Path(checkpoint['path']), checkpoint.get('sha256')
    for item in file_rows:
        if isinstance(item, dict) and isinstance(item.get('destination'), str):
            yield Path(item['destination']), item.get('destinationSha256')
    # The new Qwen training plan embeds its actual base manifest; focus manifests
    # embed the source encoder. Old generator entries in mixed lineage are not
    # treated as active assets and are intentionally not traversed here.
    for key in ('model', 'encoder'):
        if isinstance(value.get(key), dict):
            yield from manifest_assets(path, value[key])
    models = value.get('models')
    if isinstance(models, dict) and isinstance(models.get('encoder'), dict):
        yield from manifest_assets(path, models['encoder'])
    for key in ('modelManifest', 'runtimeManifest', 'tokenizerParity', 'dataMigration', 'sourceIndex'):
        item = value.get(key)
        if isinstance(item, dict) and isinstance(item.get('path'), str):
            yield Path(item['path']), item.get('sha256')
    if isinstance(value.get('textBackend'), dict):
        yield from manifest_assets(path, value['textBackend'])
    snapshot = value.get('dataSnapshot')
    for item in snapshot.values() if isinstance(snapshot, dict) else []:
        if isinstance(item, dict) and isinstance(item.get('path'), str):
            yield Path(item['path']), item.get('sha256')
    if isinstance(value.get('provenance'), dict):
        strict = value['provenance'].get('strictValidation', {})
        if isinstance(strict, dict) and isinstance(strict.get('proofPath'), str):
            yield Path(strict['proofPath']), strict.get('proofSha256')
    for item in file_rows:
        if not isinstance(item, dict):
            continue
        for path_key, hash_key in (('originalPath', 'originalSha256'), ('compressedPath', 'compressedSha256'),
                                   ('gzipPath', 'gzipSha256'), ('retainedAs', 'sha256')):
            if isinstance(item.get(path_key), str):
                yield Path(item[path_key]), item.get(hash_key, item.get('sha256') if path_key == 'originalPath' else None)
        if 'gzipPath' in item or value.get('schema') == 'jity-quarantined-registration-v1':
            if isinstance(item.get('path'), str):
                yield Path(item['path']), item.get('sha256')


def selected_paths(root, cache):
    artifact = root / 'artifacts/world-components-logic'
    selected = set()
    for name in ('qwen-short', 'short-semantics', 'short-semantics-20261109'):
        selected.update(p for p in (artifact / name).rglob('*') if p.is_file())
    selected.update(p for p in (root / 'experiments/world-components-logic/data/short-semantics/time-choice-v2').rglob('*') if p.is_file())
    for parent in (root / '.local/world-components-logic/focus-encoder-models/short-encoder-focus-20261109-r6',
                   cache / 'webgpu', cache / 'encoder'):
        if parent.exists():
            selected.update(p for p in parent.rglob('*.json') if p.name.endswith('manifest.json')
                            or p.name == 'provider.json' or p.name.startswith('copy-manifest-'))
    # Runtime/model manifests are bounded metadata; this does not traverse a venv
    # or import a model. Each referenced weight is indexed separately below.
    return {p.resolve() for p in selected}


def read_metadata(path):
    """Bound metadata memory and never implicitly hydrate a cloud placeholder."""
    if cloud_placeholder(path):
        return None, 'cloud_placeholder_not_hydrated'
    if path.suffix != '.gz' and path.stat().st_size > MAX_METADATA_BYTES:
        return None, 'large_record_metadata_not_loaded'
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rb') as stream:
        raw = stream.read(MAX_METADATA_BYTES + 1)
    if len(raw) > MAX_METADATA_BYTES:
        return None, 'large_decompressed_record_metadata_not_loaded'
    value = json.loads(raw)
    return (compact_record(value) if is_record(path) else value), None


def run_entries(paths, documents, file_rows, root=BASE):
    rows = {Path(row['path']): row for row in file_rows}
    answer = []
    for path in sorted(p for p in paths if p.name.endswith(PLAN_SUFFIXES)):
        plan = documents.get(path, {})
        expected = record_for_plan(path)
        records = [candidate for candidate in (expected, Path(str(expected) + '.gz')) if candidate in paths]
        record_path = next((candidate for candidate in records if candidate in documents), None)
        observed = documents.get(record_path, {})
        prefix = path.name.removesuffix('.export-plan.json').removesuffix('.plan.json')
        summaries = [path.with_name(prefix + suffix) for suffix in ('.summary.json', '.failure-summary.json')]
        summary_path = next((candidate for candidate in summaries if candidate in documents), None)
        evidence = observed or documents.get(summary_path, {})
        status = evidence.get('status', 'record_metadata_unavailable' if records else 'registered_not_executed')
        plan_sha = rows.get(path, {}).get('sha256')
        dispositions = []
        for candidate, document in documents.items():
            if not isinstance(document, dict) or candidate == record_path:
                continue
            linked = (document.get('planSha256') == plan_sha if plan_sha else False)
            if document.get('previousPath'):
                linked = linked or (resolve_reference(document['previousPath'], root) == path
                    and document.get('previousSha256') == plan_sha and plan_sha is not None)
            if linked and (document.get('status') in NO_EXECUTION or category(candidate) == 'disposition_evidence'):
                dispositions.append({'path': str(candidate), 'status': document.get('status'),
                    'reason': document.get('reason'), 'modelCalls': document.get('modelCalls')})
        disposition = next((item for item in reversed(dispositions) if item.get('reason')), None)
        effective = disposition['status'] if disposition else status
        no_execution_proof = effective in NO_EXECUTION and (
            (evidence.get('modelCalls') == 0 and type(evidence.get('modelCalls')) is int
             and bool(evidence.get('reason')) and evidence.get('planSha256') == plan_sha and plan_sha is not None)
            or (disposition and type(disposition.get('modelCalls')) is int and disposition['modelCalls'] == 0))
        settled = effective not in NOT_FINAL | {'registered_not_executed', 'record_metadata_unavailable', None}
        if effective in NO_EXECUTION:
            settled = bool(no_execution_proof)
        answer.append({'runId': plan.get('runId', evidence.get('runId', prefix)), 'plan': str(path),
            'record': str(record_path) if record_path else None, 'retainedRecords': list(map(str, records)),
            'status': status, 'effectiveDisposition': effective, 'dispositionEvidence': dispositions,
            'summaryEvidence': str(summary_path) if summary_path else None,
            'scope': plan.get('workload', plan.get('comparison')), 'arms': plan.get('arms'),
            'readiness': plan.get('readiness'), 'finalEvidence': settled,
            'executionCompleted': effective in ('diagnostic_completed', 'completed') and effective not in NO_EXECUTION,
            'explainedWithoutExecution': bool(no_execution_proof),
            'observedRecord': observed or None})
    return answer


def build(root, cache, *, hash_weights=False, hash_raw=False):
    root, cache = Path(root).resolve(), Path(cache).resolve()
    paths = selected_paths(root, cache)
    documents, registrations, problems, omitted = {}, {}, [], []
    pending_documents, inspected = list(sorted(paths)), set()
    while pending_documents:
        path = pending_documents.pop()
        if path in inspected or not path.is_file():
            continue
        inspected.add(path)
        if path.suffix == '.json' or (path.suffix == '.gz' and is_record(path)):
            try:
                value, reason = read_metadata(path)
                if reason:
                    omitted.append({'path': str(path), 'reason': reason})
                if isinstance(value, dict):
                    documents[path] = value
                    for asset, expected in manifest_assets(path, value):
                        asset = resolve_reference(asset, root)
                        registrations.setdefault(asset, []).append({'manifest': str(path), 'expectedSha256': expected})
                        if asset.suffix == '.json' and asset not in inspected:
                            pending_documents.append(asset)
            except (OSError, json.JSONDecodeError, EOFError) as error:
                problems.append({'kind': 'unreadable_or_live_json', 'path': str(path), 'error': str(error)})
    paths.update(registrations)
    retained = {}
    for source, value in documents.items():
        source_files = value.get('files')
        for item in source_files if isinstance(source_files, list) else []:
            if not isinstance(item, dict):
                continue
            if (value.get('schema') == 'jity-quarantined-relocation-v2'
                    and item.get('originalPath') and item.get('retainedAs') and item.get('sha256')):
                retained[resolve_reference(item['originalPath'], root)] = {
                    'path': str(resolve_reference(item['retainedAs'], root)), 'sha256': item['sha256'],
                    'evidence': str(source), 'meaning': 'quarantined_not_qualified'}
            original = item.get('originalPath', item.get('path'))
            compressed = item.get('compressedPath', item.get('gzipPath'))
            if (original and compressed and (value.get('lossless') is True or item.get('decompressedByteIdentityVerified') is True)):
                retained[resolve_reference(original, root)] = {
                    'path': str(resolve_reference(compressed, root)),
                    'sha256': item.get('compressedSha256', item.get('gzipSha256')),
                    'originalSha256': item.get('originalSha256', item.get('sha256')),
                    'evidence': str(source), 'meaning': 'lossless_compressed_record_prior_verification'}
    tracked, ignored = git_state(root, sorted(paths))
    files = []
    for path in sorted(paths):
        row = file_entry(path, root, hash_weights=hash_weights, hash_raw=hash_raw)
        row['registeredBy'] = registrations.get(path, [])
        row['tracked'] = row.get('relativePath') in tracked
        row['ignored'] = row.get('relativePath') in ignored if row.get('relativePath') else None
        row['outsideRepository'] = not path.is_relative_to(root)
        if path in retained:
            row['retainedAs'] = retained[path]
        if row['type'].endswith('_local_only'):
            if row['tracked']:
                problems.append({'kind': 'local_only_file_tracked', 'path': str(path)})
            if not row['outsideRepository'] and not row['ignored']:
                problems.append({'kind': 'local_only_file_not_ignored', 'path': str(path)})
        if not row['exists']:
            alternative = retained.get(path)
            expected_original = alternative.get('originalSha256', alternative.get('sha256')) if alternative else None
            if (not alternative or not Path(alternative['path']).is_file()
                    or any(ref['expectedSha256'] and ref['expectedSha256'] != expected_original for ref in row['registeredBy'])):
                problems.append({'kind': 'registered_asset_missing', 'path': str(path)})
        if row.get('stableDuringRead') is False:
            problems.append({'kind': 'live_file_changed_during_hash', 'path': str(path)})
        if row.get('sha256'):
            for ref in row['registeredBy']:
                if ref['expectedSha256'] and ref['expectedSha256'] != row['sha256']:
                    problems.append({'kind': 'registered_hash_mismatch', 'path': str(path), 'manifest': ref['manifest']})
        files.append(row)
    identities = []
    for path, value in documents.items():
        if category(path) in ('provider_identity', 'identity_index') and ('modelId' in value
                or 'identity' in value or 'provider' in path.name):
            identities.append({'path': str(path), **{key: value[key] for key in ('runId', 'schema',
                'modelId', 'revision', 'identity', 'arm', 'trainingSteps', 'datasetSha256',
                'semanticQualityApproved', 'checkpoint', 'textBackend') if key in value}})
    runs = run_entries(paths, documents, files, root)
    pending = [r['runId'] for r in runs if not r['finalEvidence']]
    return {'schema': 'jity-short-delivery-evidence-index-v2-draft',
        'createdAt': datetime.now(timezone.utc).isoformat(), 'workspace': str(root),
        'scope': 'read_only_identity_and_retention_index_not_semantic_approval',
        'modelExecutions': 0, 'weightByteVerificationRequested': hash_weights,
        'rawByteVerificationRequested': hash_raw,
        'historicalInventoryPreserved': str(root / 'artifacts/world-components-logic/short-semantics/data-model-inventory.json'),
        'activeGeneratorPolicy': 'Qwen3-0.6B non-thinking WebGPU; Randeng historical only, no fallback',
        'semanticQualityApproved': False, 'productionIntegration': False,
        'fullRequest500ms': 'not_measured_with_actual_AB_C_and_ready',
        'humanReviewCount': 0, 'sourceVerification': 'unverified_assistant_drafts_open_holdout',
        'files': files, 'runs': runs, 'modelAndRuntimeRegistrations': identities,
        'dispositionDocuments': [{'path': str(path), 'schema': value.get('schema'), 'status': value.get('status'),
            'reason': value.get('reason')} for path, value in documents.items() if category(path) == 'disposition_evidence'],
        'metadataNotRead': omitted,
        'evidenceNotRehashed': [{'path': row['path'], 'reason': row.get('verification'),
            'registeredHashes': [ref for ref in row.get('registeredBy', []) if ref.get('expectedSha256')]}
            for row in files if row['exists'] and not row.get('sha256')],
        'pendingRuns': pending, 'problems': problems,
        'readyForFinalIndex': not pending and not problems,
        'limits': ['File hashes are point-in-time observations, not semantic judgments.',
                  'A raw log retained on disk does not prove every intended output was recorded.',
                  'Default raw/weight indexing records metadata and prior registered hashes, not fresh byte verification.',
                  'Cloud placeholders are not hydrated; unavailable run metadata stays explicitly unresolved.',
                  'Qwen r2 has 44 documented raw output gaps; do not fabricate missing text.',
                  'MPS training/diagnosis and ONNX browser inference are distinct model and cost scopes.',
                  'New Qwen task training and browser evidence must be read from final run records.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=BASE)
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/jity-d-short-semantics-20261109')
    parser.add_argument('--verify-model-bytes', action='store_true')
    parser.add_argument('--verify-raw-bytes', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    index = build(args.root, args.cache, hash_weights=args.verify_model_bytes, hash_raw=args.verify_raw_bytes)
    if args.final and not index['readyForFinalIndex']:
        raise SystemExit('Final index refused: pending runs or retention/identity problems remain.')
    if args.output:
        if args.output.exists():
            raise SystemExit('Refusing to overwrite an existing inventory.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(index, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    else:
        print(json.dumps({k: index[k] for k in ('schema', 'pendingRuns', 'problems', 'readyForFinalIndex')}
            | {'fileCount': len(index['files']), 'runs': [{k: r[k] for k in ('runId', 'status')} for r in index['runs']]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
