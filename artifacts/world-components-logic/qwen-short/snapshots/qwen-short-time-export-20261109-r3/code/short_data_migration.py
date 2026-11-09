"""Verify exact, non-semantic data lineage for the D08 input correction.

No label is inferred here. Unchanged tasks may retain their original training
provenance; changed tasks need a separately registered real training batch.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from lab import sha256_file
from short_contracts import digest

SCHEMA = 'jity-d-time-choice-input-migration-v1'
CHANGED = {'D08.1.unit', 'D08.1.amount', 'D08.2.time.unit', 'D08.2.time.amount'}
UNITS = {'second', 'minute', 'hour', 'day', 'month', 'year'}


def _packet(spec):
    path = Path(spec['path'])
    if sha256_file(path) != spec['sha256']:
        raise ValueError('migration_dataset_bytes_changed')
    raw = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec['uncompressedSha256']:
        raise ValueError('migration_uncompressed_bytes_changed')
    lines = raw.splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    ids = [row['exampleId'] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('migration_duplicate_example_id')
    for row in rows:
        if digest({key: value for key, value in row.items() if key != 'contentSha256'}) != row['contentSha256']:
            raise ValueError('migration_row_content_hash_changed')
    return rows, lines


def verify_migration(path, *, source_sha=None, target_sha=None, unchanged_components=()):
    path = Path(path)
    proof = json.loads(path.read_text())
    if proof.get('schema') != SCHEMA or set(proof.get('allowedChangedComponents', [])) != CHANGED:
        raise ValueError('unregistered_data_migration')
    if proof.get('allowedChangedFields') != ['input', 'contentSha256']:
        raise ValueError('migration_field_policy_changed')
    source, target = proof['sourceDataset'], proof['targetDataset']
    if source_sha is not None and source['sha256'] != source_sha:
        raise ValueError('migration_source_identity_mismatch')
    if target_sha is not None and target['sha256'] != target_sha:
        raise ValueError('migration_target_identity_mismatch')
    requested = set(unchanged_components)
    if requested & CHANGED:
        raise ValueError('changed_task_requires_new_training')
    old, old_lines = _packet(source)
    new, new_lines = _packet(target)
    registered = proof['rows']
    if not old or not (len(old) == len(new) == len(registered) == proof['rowCount']):
        raise ValueError('migration_row_coverage_mismatch')
    previous = {}
    for row in old:
        key = (row['component'], row.get('derivedFromAnnotation'), digest(row['input']))
        previous.setdefault(key, set()).add(digest(row['target']))
    changed = 0
    task_counts = {}
    for index, (before, after, record) in enumerate(zip(old, new, registered)):
        component = before['component']
        task_counts[component] = task_counts.get(component, 0) + 1
        if digest({k: v for k, v in before.items() if k not in ('input', 'contentSha256')}) != digest({
                k: v for k, v in after.items() if k not in ('input', 'contentSha256')}):
            raise ValueError('migration_noninput_field_changed')
        is_changed = digest(before) != digest(after)
        if component in CHANGED and not is_changed:
            raise ValueError('migration_time_task_not_updated')
        if is_changed:
            changed += 1
            if component not in CHANGED:
                raise ValueError('migration_unregistered_task_changed')
            if not isinstance(after['input'], dict) or 'timeChoice' in before['input']:
                raise ValueError('migration_time_choice_shape')
            if digest({k: v for k, v in after['input'].items() if k != 'timeChoice'}) != digest(before['input']):
                raise ValueError('migration_original_input_changed')
            choice = after['input'].get('timeChoice')
            expected_keys = {'boundary'} if component.endswith('.unit') else {'boundary', 'unit'}
            if not isinstance(choice, dict) or set(choice) != expected_keys or choice['boundary'] != 'elapsed':
                raise ValueError('migration_time_choice_shape')
            if 'unit' in choice and choice['unit'] not in UNITS:
                raise ValueError('migration_invalid_time_unit')
            prefix = component.rsplit('.', 1)[0]
            for dependency in expected_keys:
                key = (prefix + '.' + dependency, before.get('derivedFromAnnotation'), digest(before['input']))
                if previous.get(key) != {digest(choice[dependency])}:
                    raise ValueError('migration_previous_choice_reference_mismatch:' + dependency)
        elif old_lines[index] != new_lines[index]:
            raise ValueError('migration_unaffected_raw_bytes_changed')
        expected = {'rowIndex': index, 'oldExampleId': before['exampleId'], 'newExampleId': after['exampleId'],
            'component': component, 'sourceGroup': before['sourceGroup'], 'split': before['split'],
            'oldInputSha256': digest(before['input']), 'newInputSha256': digest(after['input']),
            'oldTargetSha256': digest(before['target']), 'newTargetSha256': digest(after['target']),
            'oldContentSha256': before['contentSha256'], 'newContentSha256': after['contentSha256'],
            'oldFullRowSha256': digest(before), 'newFullRowSha256': digest(after),
            'changed': is_changed, 'unchangedFieldsExact': True}
        if digest(record) != digest(expected):
            raise ValueError('migration_row_proof_mismatch')
    if not changed or not requested <= set(task_counts):
        raise ValueError('migration_missing_changed_or_inherited_tasks')
    unchanged = len(old) - changed
    if (proof['changedRows'] != changed or proof['unaffectedRowsExactEquality'] != unchanged
            or proof['unaffectedRawLinesByteIdentical'] != unchanged):
        raise ValueError('migration_count_claim_mismatch')
    return {'path': str(path.resolve()), 'sha256': sha256_file(path), 'schema': SCHEMA,
        'sourceDatasetSha256': source['sha256'], 'targetDatasetSha256': target['sha256'],
        'rowCount': len(old), 'changedRows': changed, 'unchangedRows': unchanged,
        'verifiedUnchangedComponents': sorted(requested),
        'trainingQualification': 'original_training_identity_retained_for_unchanged_tasks_only',
        'semanticApproval': False}
