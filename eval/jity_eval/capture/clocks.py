"""Record and restore external SQLite message clock inputs, without masking HTTP.

Only session_messages.created_at is restored. Message identity/content hashes,
the actual model request body, raw responses and every gameplay field retain
their exact validation. Install the same adapter for record and replay.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.message-clocks-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False, sort_keys=True, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def identity(row):
    return {'id': int(row['id']), 'session_id': row['session_id'], 'turn_node_id': row.get('turn_node_id'),
            'role': row['role'], 'campaign_session_index': row.get('campaign_session_index'),
            'content_sha256': hashlib.sha256(row['content'].encode('utf-8')).hexdigest()}


def rows_from_connection(db, session_id):
    db.row_factory = sqlite3.Row
    return [dict(row) for row in db.execute('SELECT id,session_id,turn_node_id,role,content,campaign_session_index,created_at FROM session_messages WHERE session_id=? ORDER BY id', (session_id,))]


def _legacy_request_messages(calls_db):
    """Read clock values only from actual sent request bodies, never answers."""
    import base64
    result = []
    with sqlite3.connect(Path(calls_db).resolve().as_uri()+'?mode=ro', uri=True) as db:
        for sequence, raw, context in db.execute('SELECT sequence,request,context FROM calls ORDER BY sequence'):
            request, context = json.loads(raw), json.loads(context)
            body = request.get('body')
            if body is None:
                body = json.loads(base64.b64decode(request['body_base64']))
            for message in body.get('messages', []):
                content = message.get('content', '')
                start, end = '[STORY_MATERIAL_START]\n', '\n[STORY_MATERIAL_END]'
                if not isinstance(content, str) or start not in content:
                    continue
                material = json.loads(content.split(start,1)[1].split(end,1)[0])
                for row in material.get('最近剧情', []):
                    if 'created_at' in row:
                        result.append((sequence, context, row))
    return result


def seed_legacy_clocks(game_dir, evidence_path=None):
    """Create evidence from the original canonical DB, cross-checking raw inputs.

    This does not alter a game database or a call journal. A conflicting legacy
    observation fails closed instead of choosing a timestamp to force a match.
    Existing clock evidence is validated and never overwritten/reseeded.
    """
    game_dir = Path(game_dir).resolve()
    path = Path(evidence_path).resolve() if evidence_path else game_dir/'message-clocks.json'
    game_id = game_dir.name
    canonical = game_dir/'runtime.sqlite3'
    if not canonical.is_file():
        raise ValueError('Legacy canonical game database is missing: '+game_id)
    with sqlite3.connect(canonical.as_uri()+'?mode=ro', uri=True) as db:
        rows = rows_from_connection(db, game_id)
    by_id = {row['id']: row for row in rows}
    observed = _legacy_request_messages(game_dir/'calls.sqlite3')
    checks = []
    for sequence, context, observed_row in observed:
        actual = by_id.get(observed_row['id'])
        if actual is None:
            raise ValueError('Raw request refers to a message absent from canonical DB')
        for key in ('id','role','content','campaign_session_index','created_at'):
            if observed_row.get(key) != actual.get(key):
                raise ValueError('Legacy DB/raw-request clock or identity mismatch at call %s message %s field %s' % (sequence, actual['id'], key))
        if context.get('game_id') != game_id:
            raise ValueError('Raw clock evidence belongs to another game')
        checks.append({'call_sequence': sequence, 'message_id': actual['id'], 'created_at': actual['created_at'],
                       'content_sha256': hashlib.sha256(actual['content'].encode()).hexdigest()})
    entries = {str(row['id']): {**identity(row), 'created_at': row['created_at'], 'provenance': 'legacy_canonical_database'} for row in rows}
    if path.exists():
        existing = json.loads(path.read_text())
        for key, entry in entries.items():
            saved = existing.get('entries', {}).get(key)
            if saved is None or {k:saved.get(k) for k in entry if k!='provenance'} != {k:v for k,v in entry.items() if k!='provenance'}:
                raise ValueError('Existing clock evidence differs; refusing to overwrite')
        return existing
    manifest = json.loads((game_dir.parent/'manifest.json').read_text())
    document = {'schema_version': 1, 'kind':'recorded_message_clock_inputs', 'game_id':game_id,
                'manifest_sha256':digest(manifest), 'entries':entries,
                'created_at':datetime.now(timezone.utc).isoformat(),
                'legacy_provenance':{'database_path':'runtime.sqlite3',
                    'database_sha256':hashlib.sha256(canonical.read_bytes()).hexdigest(),
                    'raw_request_clock_checks':checks,
                    'clock_observed_in_raw_requests':bool(checks),
                    'note':'Identity, complete message content and created_at cross-checked for every raw ending-material observation. Other message times come only from the recorded canonical DB.'}}
    atomic_json(path, document)
    return document


class Installation:
    def __init__(self, runtime_class, start, generate, reload_method, evidence_path=None):
        self.runtime_class = runtime_class
        self.original_start, self.original_generate, self.original_reload = start, generate, reload_method
        self.evidence_path = Path(evidence_path).resolve() if evidence_path else None
        self.metadata = {'kind':'recorded_message_clock_input_adapter','version':1,
                         'restored_field':'session_messages.created_at','identity_and_content_checked':True,
                         'request_matching_unchanged':True,'raw_response_substitution':False}

    def set_evidence_path(self, path):
        self.evidence_path = Path(path).resolve()

    def uninstall(self):
        if getattr(self.runtime_class, '_message_clock_adapter', None) is self:
            self.runtime_class.start = self.original_start
            self.runtime_class.generate = self.original_generate
            self.runtime_class.reload = self.original_reload
            delattr(self.runtime_class, '_message_clock_adapter')


def install_clock_adapter(runtime_class=None, *, evidence_path=None):
    from jity_eval.capture.journal import MissingCapture, UncertainCapture
    if runtime_class is None:
        from jity_eval.capture.runtime import JityRuntime
        runtime_class = JityRuntime
    prior = getattr(runtime_class, '_message_clock_adapter', None)
    if prior is not None:
        if evidence_path is not None:
            prior.set_evidence_path(evidence_path)
        return prior
    start, generate, reload_method = runtime_class.start, runtime_class.generate, runtime_class.reload
    handle = Installation(runtime_class, start, generate, reload_method, evidence_path)

    def fatal(runtime, message, missing=False):
        error = MissingCapture(message) if missing else UncertainCapture(message)
        runtime.transport.fatal = error
        raise error

    def state_for(runtime):
        cached = getattr(runtime, '_message_clock_state', None)
        if cached is not None:
            return cached
        raw_path = runtime.config.get('message_clock_path') or handle.evidence_path
        if raw_path is None:
            fatal(runtime, 'Explicit recorded message-clock evidence path is required', missing=True)
        path = Path(raw_path).resolve()
        if path.exists():
            document = json.loads(path.read_text())
            if document.get('kind') != 'recorded_message_clock_inputs' or document.get('schema_version') != 1 or document.get('game_id') != runtime.session_id:
                fatal(runtime, 'Message-clock evidence schema/game identity mismatch')
            manifest_path = path.parent.parent/'manifest.json'
            if not manifest_path.is_file() and getattr(runtime, 'root', None) is not None:
                manifest_path = Path(runtime.root).parents[1]/'manifest.json'
            if manifest_path.is_file():
                if document.get('manifest_sha256') != digest(json.loads(manifest_path.read_text())):
                    fatal(runtime, 'Message-clock evidence belongs to a different frozen manifest')
            elif document.get('manifest_sha256') is not None:
                fatal(runtime, 'Clock evidence manifest cannot be verified')
        elif runtime.transport.mode == 'replay':
            fatal(runtime, 'Missing recorded message-clock evidence', missing=True)
        else:
            # Legacy recorded prefixes must be seeded from genuine original
            # metadata before reconstruction, not assigned today's clock.
            if runtime.transport._prefix:
                fatal(runtime, 'Existing raw capture requires verified legacy clock seeding', missing=True)
            manifest_path = path.parent.parent/'manifest.json'
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
            document = {'schema_version':1,'kind':'recorded_message_clock_inputs','game_id':runtime.session_id,
                        'manifest_sha256':digest(manifest) if manifest else None, 'entries':{},
                        'created_at':datetime.now(timezone.utc).isoformat(),
                        'provenance':'Recorded from actual committed runtime database before subsequent model requests'}
            atomic_json(path, document)
        cached = runtime._message_clock_state = {'path':path,'document':document}
        return cached

    def reconcile(runtime, *, final=False):
        state = state_for(runtime)
        document, path = state['document'], state['path']
        with runtime.db.connect() as db:
            rows = rows_from_connection(db, runtime.session_id)
        added, updates = [], []
        for row in rows:
            key, observed_identity = str(row['id']), identity(row)
            entry = document['entries'].get(key)
            if entry is None:
                if runtime.transport.mode == 'replay':
                    fatal(runtime, 'Missing recorded clock for message '+key, missing=True)
                entry = {**observed_identity,'created_at':row['created_at'],'provenance':'recorded_runtime_database'}
                document['entries'][key] = entry
                added.append(entry)
            elif any(entry.get(field) != value for field,value in observed_identity.items()):
                fatal(runtime, 'Recorded message clock identity/content mismatch for message '+key)
            if not isinstance(entry.get('created_at'),str) or not entry['created_at']:
                fatal(runtime, 'Recorded message clock is missing for message '+key, missing=True)
            if row['created_at'] != entry['created_at']:
                updates.append((entry['created_at'],row['id'],row['created_at']))
        # Publish every newly observed time before returning from generate,
        # hence before any next-turn request can consume those messages.
        if added:
            atomic_json(path, document)
            for entry in added:
                runtime._event('message_clock_recorded', {'clock_evidence_path':str(path),'entry':entry})
        if updates:
            with runtime.db.connect() as db:
                for timestamp, row_id, previous in updates:
                    db.execute('UPDATE session_messages SET created_at=? WHERE session_id=? AND id=?',
                               (timestamp,runtime.session_id,row_id))
            for timestamp,row_id,previous in updates:
                runtime._event('message_clock_restored', {'clock_evidence_path':str(path),'message_id':row_id,
                                                         'discarded_reconstruction_clock':previous,'recorded_clock':timestamp,
                                                         'identity_and_content_verified':True})
        if final and runtime.transport.mode == 'replay' and {str(row['id']) for row in rows} != set(document['entries']):
            fatal(runtime, 'Unused or missing message-clock evidence after full replay')

    async def observed_start(runtime, *args, **kwargs):
        result = await start(runtime, *args, **kwargs)
        reconcile(runtime)
        return result

    async def observed_generate(runtime, payload):
        reconcile(runtime)
        try:
            return await generate(runtime, payload)
        finally:
            # Preserve a durable clock even if a committed turn's later
            # background observation raises; never catch or suppress the error.
            reconcile(runtime)

    async def observed_reload(runtime, *args, **kwargs):
        reconcile(runtime, final=True)
        return await reload_method(runtime, *args, **kwargs)

    runtime_class.start, runtime_class.generate, runtime_class.reload = observed_start, observed_generate, observed_reload
    runtime_class._message_clock_adapter = handle
    return handle
