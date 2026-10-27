"""Transactional A3 storage using the existing A2 control adapter.

The A2 core adapter, constrained relational ledger and authoritative work
repository commit together. Active work is reconstructed from SQL, not the
core adapter snapshot. Authority, judgments, frozen copies and reserved work
share the same transaction and are checked against their relational records.
No pickle or executable object deserialization is used.
"""
import copy
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel

from app.schemas.world.contracts import TimelinePoint, WorldState
from app.schemas.world.v2.contexts import WorkingProgress
from app.schemas.world.v2.work import SettlementGroup
from app.database.world_repository import LedgerMismatch, check_core, replay_state, save_core, wire
from app.services.world.store import WorldNotFound
from app.database.world_work_repository import (
    check_work, initialize_work_schema, install_work_guards, load_work, load_reserved_work, save_work,
)

_MODELS = {model.__name__: model for model in (
    WorldState, TimelinePoint, WorkingProgress, SettlementGroup)}


class PersistentWorldRecord(dict):
    """A record with a transaction clock, outside its persisted dictionary.

    Integer clock/TTL attributes survive deepcopy without copying a live
    connection or thread-local store. Equality remains about durable facts.
    """
    def __init__(self, value=(), *, now=0, lease_ttl=120_000, claim_ttl=180_000):
        super().__init__(value)
        self.now = now
        self.lease_ttl_milli = lease_ttl
        self.claim_ttl_milli = claim_ttl

    def clock_milli(self):
        return self.now


def _encode(value):
    if isinstance(value, BaseModel):
        if type(value) not in _MODELS.values():
            raise TypeError(f'Unsupported world record model: {type(value).__name__}')
        return ['model', type(value).__name__, value.model_dump(mode='json')]
    if isinstance(value, dict):
        return ['dict', [[_encode(key), _encode(item)] for key, item in value.items()]]
    if isinstance(value, tuple):
        return ['tuple', [_encode(item) for item in value]]
    if isinstance(value, list):
        return ['list', [_encode(item) for item in value]]
    if value is None or type(value) in (str, int, bool):
        return ['scalar', value]
    raise TypeError(f'Unsupported world record value: {type(value).__name__}')


def _decode(value):
    tag = value[0]
    if tag == 'model':
        return _MODELS[value[1]].model_validate(value[2])
    if tag == 'dict':
        return {_decode(key): _decode(item) for key, item in value[1]}
    if tag == 'tuple':
        return tuple(_decode(item) for item in value[1])
    if tag == 'list':
        return [_decode(item) for item in value[1]]
    if tag == 'scalar':
        return value[1]
    raise ValueError(f'Unknown world snapshot tag: {tag}')


def _dump(value):
    return json.dumps({'format': 1, 'value': _encode(value)}, ensure_ascii=False,
                      allow_nan=False, separators=(',', ':'))


def _load(raw):
    document = json.loads(raw)
    if document['format'] != 1:
        raise ValueError('Unsupported world snapshot format')
    return _decode(document['value'])


class SQLiteBaselineStore:
    """One BEGIN IMMEDIATE transaction per write, also across store instances.

    locked() spans creation, ID allocation and global idempotency together.
    Reentrant calls use that same connection/transaction. Connections are
    short lived; no in-process cache survives between reads or transactions.
    """

    persistent = True

    def __init__(self, path, clock=None):
        self.path = str(Path(path).expanduser().resolve())
        self._clock = clock or (lambda: time.time_ns() // 1_000_000)
        self._local = threading.local()
        # The caller selects/creates the parent directory explicitly.
        with self._connection() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS world_snapshot_meta (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    format INTEGER NOT NULL CHECK(format=1),
                    sequence INTEGER NOT NULL CHECK(sequence>=0)
                );
                INSERT OR IGNORE INTO world_snapshot_meta VALUES(1,1,0);
                CREATE TABLE IF NOT EXISTS world_snapshots (
                    world_id TEXT PRIMARY KEY, record_json TEXT NOT NULL
                    CHECK(json_valid(record_json))
                );
                CREATE TABLE IF NOT EXISTS world_creation_replays (
                    request_id TEXT PRIMARY KEY, entry_json TEXT NOT NULL
                    CHECK(json_valid(entry_json))
                );
            ''')
            self._initialize_core(connection)

    @staticmethod
    def _initialize_core(connection):
        """Install the frozen DDL transactionally, without executescript's COMMIT.

        A3-1 snapshots cannot reconstruct discarded old round metadata. Do not
        silently fabricate that history during an automatic migration.
        """
        connection.execute('BEGIN IMMEDIATE')
        try:
            installed = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_core_schema'").fetchone()
            if installed:
                if connection.execute('SELECT version FROM world_core_schema').fetchall() != [(1,)]:
                    raise ValueError('Unsupported world core schema version')
            else:
                if connection.execute('SELECT count(*) FROM world_snapshots').fetchone()[0]:
                    raise ValueError('Nonempty A3-1 snapshot database requires explicit migration; '
                                     'use a new development database path')
                script = Path(__file__).with_name('world_storage_v2.sql').read_text(encoding='utf-8')
                statement = ''
                for line in script.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        connection.execute(statement)
                        statement = ''
                if statement.strip():
                    raise ValueError('Incomplete world core migration SQL')
                connection.execute('CREATE TABLE world_core_schema(version INTEGER NOT NULL CHECK(version=1))')
                connection.execute('INSERT INTO world_core_schema VALUES(1)')
            work_schema = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_work_schema'").fetchone()
            if work_schema:
                if connection.execute('SELECT version FROM world_work_schema').fetchall() != [(1,)]:
                    raise ValueError('Unsupported world work schema version')
            else:
                if connection.execute('SELECT count(*) FROM world_snapshots').fetchone()[0]:
                    raise ValueError('Nonempty A3-2 core database requires explicit work migration; '
                                     'use a new development database path')
                initialize_work_schema(connection)
                connection.execute('CREATE TABLE world_work_schema(version INTEGER NOT NULL CHECK(version=1))')
                connection.execute('INSERT INTO world_work_schema VALUES(1)')
            install_work_guards(connection)
            authority = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_authority_schema'").fetchone()
            if not authority:
                if connection.execute('SELECT count(*) FROM world_snapshots').fetchone()[0]:
                    raise ValueError('Nonempty development database requires explicit authority migration; '
                                     'use a new development database path')
                connection.execute('''CREATE TABLE world_authority_meta (
                    world_id TEXT PRIMARY KEY REFERENCES worlds(id),
                    highest_epoch INTEGER NOT NULL CHECK(highest_epoch>0),
                    blocked_reason TEXT CHECK(blocked_reason IN ('claim_expired','claim_fenced'))
                ) STRICT''')
                connection.execute('CREATE TABLE world_authority_schema(version INTEGER NOT NULL CHECK(version=1))')
                connection.execute('INSERT INTO world_authority_schema VALUES(1)')
            elif connection.execute('SELECT version FROM world_authority_schema').fetchall() != [(1,)]:
                raise ValueError('Unsupported world authority schema version')
            from app.database.world_frozen_repository import initialize_frozen_schema
            initialize_frozen_schema(connection)
            from app.database.world_judgment_repository import initialize_judgment_schema
            initialize_judgment_schema(connection)
            from app.database.world_progress_repository import initialize_progress_schema
            initialize_progress_schema(connection)
            connection.execute('''CREATE TRIGGER IF NOT EXISTS authority_epoch_monotone
                BEFORE UPDATE ON world_authority_meta WHEN NEW.highest_epoch<OLD.highest_epoch
                BEGIN SELECT RAISE(ABORT,'authority_epoch_cannot_decrease'); END''')
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=getattr(self, 'busy_timeout', 30), isolation_level=None)
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA synchronous=FULL')
            yield connection
        finally:
            connection.close()

    def clock_milli(self):
        return int(self._clock())

    def prepare_record(self, record):
        return PersistentWorldRecord(record, now=self.clock_milli(),
            lease_ttl=getattr(self, 'lease_ttl_milli', 120_000),
            claim_ttl=getattr(self, 'claim_ttl_milli', 180_000))

    @contextmanager
    def locked(self):
        if getattr(self._local, 'connection', None) is not None:
            yield
            return
        with self._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as error:
                if 'locked' in str(error).lower() or 'busy' in str(error).lower():
                    from app.services.world.control import ServiceRefusal
                    raise ServiceRefusal('request_in_progress', 'world transaction is already in progress') from error
                raise
            self._local.connection = connection
            try:
                yield
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                del self._local.connection

    def next_id(self, kind):
        with self.locked():
            connection = self._local.connection
            connection.execute('UPDATE world_snapshot_meta SET sequence=sequence+1 WHERE singleton=1')
            sequence = connection.execute(
                'SELECT sequence FROM world_snapshot_meta WHERE singleton=1').fetchone()[0]
            return f'{kind}_{sequence}'

    def create_world(self, world_id, record):
        with self.locked():
            save_core(self._local.connection, None, record)
            save_work(self._local.connection, None, record)
            check_core(self._local.connection, record)
            self._local.connection.execute(
                'INSERT INTO world_snapshots VALUES(?,?)', (world_id, self._dump_record(record)))

    @staticmethod
    def _dump_record(record):
        # The relational work tables are authoritative. Do not leave a second
        # work copy inside the A2-compatible core adapter snapshot.
        stored = {key: value for key, value in record.items()
                  if key not in ('work', '_successorWork', '_groupProgress')}
        # Authority-only loads keep the pointer fields from the snapshot;
        # full loads own them from the relational work rows below.
        if 'work' in record:
            stored['_activeWorkPointId'] = (record.get('work') or {}).get('pointId')
            stored['_reservedWorkPointId'] = (record.get('_successorWork') or {}).get('pointId')
        return _dump(stored)

    def world(self, world_id, *, authority_only=False):
        connection = getattr(self._local, 'connection', None)
        if connection is not None:
            return self._read_world(connection, world_id, authority_only=authority_only)
        # One read transaction: a concurrent writer must not create a false
        # corruption report between the cache read and ledger checks.
        with self._connection() as reader:
            reader.execute('BEGIN')
            return self._read_world(reader, world_id, authority_only=authority_only)

    def _read_world(self, connection, world_id, *, authority_only=False):
        try:
            return self._load_world_record(connection, world_id, authority_only=authority_only)
        except LedgerMismatch:
            raise
        except (ValueError, TypeError, KeyError) as error:
            # Validation failures here describe saved SQL data, after request
            # validation. Keep them on the same corruption/refusal path.
            raise LedgerMismatch('Persistent world record is malformed') from error

    def _load_world_record(self, connection, world_id, *, authority_only=False):
        row = connection.execute('SELECT record_json FROM world_snapshots WHERE world_id=?',
                                 (world_id,)).fetchone()
        if row is None:
            return None
        record = self.prepare_record(_load(row[0]))
        if '_activeWorkPointId' not in record:
            raise LedgerMismatch('Working-pointer binding is missing; explicit migration required')
        if authority_only:
            # Lease authority must survive damaged frozen/progress/judgment
            # facts: the next protected read (get_context) is the operation
            # that reports frozen_work_*, with its own declared error surface.
            # Active work is still loaded for an accurate response view, but
            # its progress/frozen side tables are deliberately not validated.
            check_core(connection, record)
            record['work'] = load_work(connection, world_id)
            reserved = load_reserved_work(connection, world_id)
            if reserved is not None:
                record['_successorWork'] = reserved
            if (record['work'] or {}).get('pointId') != record.get('_activeWorkPointId'):
                raise LedgerMismatch('Relational work differs from the bound active point')
            if (reserved or {}).get('pointId') != record.get('_reservedWorkPointId'):
                raise LedgerMismatch('Reserved work differs from its bound successor pointer')
            check_work(connection, record)
            return record
        expected_work_point = record.pop('_activeWorkPointId')
        expected_reserved_point = record.pop('_reservedWorkPointId', None)
        record['work'] = load_work(connection, world_id)
        reserved = load_reserved_work(connection, world_id)
        if reserved is not None:
            record['_successorWork'] = reserved
        if (reserved or {}).get('pointId') != expected_reserved_point:
            raise LedgerMismatch('Reserved work differs from its bound successor pointer')
        if (record['work'] or {}).get('pointId') != expected_work_point:
            raise LedgerMismatch('Relational work differs from the bound active point')
        from app.database.world_progress_repository import load_progress, check_progress
        record['_groupProgress'] = load_progress(connection, record)
        check_core(connection, record)
        check_work(connection, record)
        from app.database.world_frozen_repository import check_frozen_work
        check_frozen_work(connection, record)
        from app.database.world_judgment_repository import check_judgments
        check_progress(connection, record)
        check_judgments(connection, record)
        return record

    def transact(self, world_id, handler, *, authority_only=False):
        with self.locked():
            snapshot = (self.world(world_id, authority_only=True)
                        if authority_only else self.world(world_id))
            if snapshot is None:
                raise WorldNotFound(world_id)
            before = copy.deepcopy(snapshot)
            response = handler(snapshot)
            if snapshot == before:
                return response
            save_core(self._local.connection, before, snapshot)
            if authority_only:
                check_core(self._local.connection, snapshot)
                check_work(self._local.connection, snapshot)
                self._local.connection.execute(
                    'UPDATE world_snapshots SET record_json=? WHERE world_id=?',
                    (self._dump_record(snapshot), world_id))
                return response
            save_work(self._local.connection, before, snapshot)
            from app.database.world_frozen_repository import save_frozen_work, check_frozen_work
            save_frozen_work(self._local.connection, before, snapshot)
            from app.database.world_progress_repository import save_progress, check_progress
            save_progress(self._local.connection, before, snapshot)
            from app.database.world_judgment_repository import save_allocations, check_judgments
            save_allocations(self._local.connection, before, snapshot)
            check_core(self._local.connection, snapshot)
            check_work(self._local.connection, snapshot)
            check_frozen_work(self._local.connection, snapshot)
            check_progress(self._local.connection, snapshot)
            check_judgments(self._local.connection, snapshot)
            if load_work(self._local.connection, world_id) != snapshot['work']:
                raise LedgerMismatch('Relational work does not reconstruct the transaction result')
            if load_reserved_work(self._local.connection, world_id) != snapshot.get('_successorWork'):
                raise LedgerMismatch('Relational successor does not reconstruct the transaction result')
            self._local.connection.execute(
                'UPDATE world_snapshots SET record_json=? WHERE world_id=?',
                (self._dump_record(snapshot), world_id))
            return response

    def operation_handler(self, operation):
        if operation == 'checkpoint_prepare_successor':
            from app.services.world.successor import handler_prepare_successor
            return handler_prepare_successor
        if operation == 'checkpoint_restore_group_work':
            def restore(store, record, request):
                from app.database.world_frozen_repository import restore_group_work
                return self._frozen_call(restore_group_work, self._local.connection, record, request)
            return restore
        if operation in ('create_rolls', 'allocate_ids'):
            from app.services.world import judgments
            return judgments.create_rolls if operation == 'create_rolls' else judgments.allocate_ids
        if operation.startswith('checkpoint_') and operation not in (
                'checkpoint_start_advance', 'checkpoint_pause', 'checkpoint_resume'):
            from app.services.world.control import WRITE_HANDLERS
            return WRITE_HANDLERS.get(operation)
        return None

    @staticmethod
    def _frozen_call(function, *args):
        from app.database.world_frozen_repository import FrozenWorkError
        from app.services.world.control import ServiceRefusal
        try:
            return function(*args)
        except FrozenWorkError as error:
            raise ServiceRefusal(error.code, str(error), error.details) from error

    def prepare_operation(self, operation, record, request):
        from app.services.world.successor import select_operation
        record._work_selection = select_operation(self, record, operation, request)
        if (hasattr(request, 'pointId') and operation.startswith('checkpoint_')
                and operation != 'checkpoint_begin_point'):
            from app.services.world.control import _bind_work_point
            _bind_work_point(record, request)
        from app.database.world_frozen_repository import require_current_payload
        if operation == 'allocate_ids':
            from app.services.world.authority import check_lease
            check_lease(self, record, request)
        excluded = ('checkpoint_pause', 'checkpoint_resume', 'checkpoint_restore_group_work',
                    'round_conclusion_cancel', 'lease_acquire', 'lease_renew', 'lease_release')
        if operation not in excluded and not operation.startswith('narration_'):
            from app.database.world_frozen_repository import FrozenWorkError
            try:
                require_current_payload(self._local.connection, record)
            except FrozenWorkError as error:
                from app.services.world.control import ServiceRefusal
                raise ServiceRefusal('phase_invalid', 'restore accepted work before continuing',
                                     {'reason': 'restore_required'}) from error

    def validate_operation(self, operation, record, request):
        from app.services.world.control import _ladder
        from app.services.world.judgments import validate_identity_bindings
        from app.database.world_judgment_repository import validate_admission, validate_group_closure
        work = None if operation in ('checkpoint_start_advance', 'checkpoint_begin_point') else record.get('work')
        _ladder(record, operation, work)
        validate_identity_bindings(self._local.connection, record, operation, request)
        if operation == 'checkpoint_extend_group' and request.admittedMember is not None:
            validate_admission(self._local.connection, record, request)
        if operation == 'checkpoint_close_group':
            validate_group_closure(self._local.connection, record, request)
        from app.services.world.progress import before_operation
        before_operation(self, record, operation, request)

    def finish_operation(self, operation, record, request, data):
        from app.services.world.progress import after_operation
        after_operation(self, record, operation, request, data)
        from app.services.world.successor import finish_operation
        finish_operation(self, record, operation, request, data, getattr(record, '_work_selection', None))
        if hasattr(record, '_work_selection'):
            del record._work_selection
        if (operation == 'checkpoint_start_advance' or
                (operation == 'round_conclusion_conclude' and request.conclusion.kind == 'continue')):
            record['round']['order'] = sorted(record['round']['order'],
                key=lambda identity: (record['state'].characters[identity].sanity, identity))

    def abort_operation(self, operation, record, request):
        from app.services.world.successor import finish_operation
        finish_operation(self, record, operation, request, None, getattr(record, '_work_selection', None))
        if hasattr(record, '_work_selection'):
            del record._work_selection

    def recovery_view(self, record, work_view):
        from app.services.world.recovery import recovery_view
        connection = getattr(self._local, 'connection', None)
        if connection is not None:
            successor_view = None
            if record.get('_successorWork') is not None:
                shadow = copy.copy(record)
                shadow['work'] = record['_successorWork']
                successor_view = work_view(shadow)
            return self._frozen_call(recovery_view, connection, record, work_view(record), successor_view)
        with self._connection() as connection:
            connection.execute('BEGIN')
            current = self._read_world(connection, record['worldId'])
            from app.services.world.authority import check_lease
            # The caller already validated the supplied credential. Hold one
            # read snapshot across record loading and protected projection.
            if current.get('lease') != record.get('lease'):
                from app.services.world.control import ServiceRefusal
                raise ServiceRefusal('lease_invalid', 'authority changed during recovery read')
            return self._frozen_call(recovery_view, connection, current, work_view(current))

    def global_idempotency(self):
        with self.locked():
            rows = self._local.connection.execute('''
                SELECT k.request_id,r.entry_json,c.world_id,c.request_hash,c.result_json
                FROM (SELECT request_id FROM world_creation_replays
                      UNION SELECT request_id FROM world_creations) k
                LEFT JOIN world_creation_replays r ON r.request_id=k.request_id
                LEFT JOIN world_creations c ON c.request_id=k.request_id''')
            return {row[0]: self._creation_entry(row[1:]) for row in rows}

    @staticmethod
    def _creation_entry(row):
        raw, world_id, digest, result = row
        if raw is None:
            if world_id is not None:
                raise LedgerMismatch('Creation result has no replay record')
            return None
        entry = _load(raw)
        expected = (entry['data']['worldId'], entry['digest'],
                    wire(dict(data=entry['data'], views=entry['views'])))
        if (world_id, digest, result) != expected:
            raise LedgerMismatch('Creation replay disagrees with relational ledger')
        return entry

    def get_creation(self, request_id):
        with self.locked():
            row = self._local.connection.execute('''
                SELECT r.entry_json,c.world_id,c.request_hash,c.result_json
                FROM (SELECT ? AS request_id) k
                LEFT JOIN world_creation_replays r ON r.request_id=k.request_id
                LEFT JOIN world_creations c ON c.request_id=k.request_id''', (request_id,)).fetchone()
            return self._creation_entry(row)

    def replay_state(self, world_id, point_id):
        with self._connection() as connection:
            connection.execute('BEGIN')
            return replay_state(connection, world_id, point_id)

    def collect_garbage(self, world_id):
        """Trusted maintenance job: retain identities, collect only terminal payloads."""
        from app.database.world_frozen_repository import collect_terminal_frozen
        from app.database.world_progress_repository import collect_terminal_progress
        with self.locked():
            counts = collect_terminal_frozen(self._local.connection, world_id)
            counts['world_group_progress'] = collect_terminal_progress(self._local.connection, world_id)
            return counts

    def note_global(self, request_id, entry):
        with self.locked():
            self._local.connection.execute(
                'INSERT INTO world_creations VALUES(?,?,?,?)',
                (request_id, entry['data']['worldId'], entry['digest'],
                 wire(dict(data=entry['data'], views=entry['views']))))
            self._local.connection.execute(
                'INSERT INTO world_creation_replays VALUES(?,?)', (request_id, _dump(entry)))
