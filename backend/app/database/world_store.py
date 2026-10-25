"""A3 storage foundation for the existing A2 record format.

The A2 core adapter, constrained relational ledger and authoritative work
repository commit together. Active work is reconstructed from SQL, not the
core adapter snapshot. Rolls, accepted manifests, TTL and takeover remain
pending; this is not the completed A3 service.
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
    check_work, initialize_work_schema, install_work_guards, load_work, save_work,
)

_MODELS = {model.__name__: model for model in (
    WorldState, TimelinePoint, WorkingProgress, SettlementGroup)}


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
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA synchronous=FULL')
            yield connection
        finally:
            connection.close()

    def clock_milli(self):
        return int(self._clock())

    @contextmanager
    def locked(self):
        if getattr(self._local, 'connection', None) is not None:
            yield
            return
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
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
        stored = {key: value for key, value in record.items() if key != 'work'}
        stored['_activeWorkPointId'] = (record.get('work') or {}).get('pointId')
        return _dump(stored)

    def world(self, world_id):
        connection = getattr(self._local, 'connection', None)
        if connection is not None:
            return self._read_world(connection, world_id)
        # One read transaction: a concurrent writer must not create a false
        # corruption report between the cache read and ledger checks.
        with self._connection() as reader:
            reader.execute('BEGIN')
            return self._read_world(reader, world_id)

    @staticmethod
    def _read_world(connection, world_id):
        row = connection.execute('SELECT record_json FROM world_snapshots WHERE world_id=?',
                                 (world_id,)).fetchone()
        if row is None:
            return None
        record = _load(row[0])
        if '_activeWorkPointId' not in record:
            raise LedgerMismatch('Working-pointer binding is missing; explicit migration required')
        expected_work_point = record.pop('_activeWorkPointId')
        record['work'] = load_work(connection, world_id)
        if (record['work'] or {}).get('pointId') != expected_work_point:
            raise LedgerMismatch('Relational work differs from the bound active point')
        check_core(connection, record)
        check_work(connection, record)
        return record

    def transact(self, world_id, handler):
        with self.locked():
            snapshot = self.world(world_id)
            if snapshot is None:
                raise WorldNotFound(world_id)
            before = copy.deepcopy(snapshot)
            response = handler(snapshot)
            if snapshot == before:
                return response
            save_core(self._local.connection, before, snapshot)
            save_work(self._local.connection, before, snapshot)
            check_core(self._local.connection, snapshot)
            check_work(self._local.connection, snapshot)
            if load_work(self._local.connection, world_id) != snapshot['work']:
                raise LedgerMismatch('Relational work does not reconstruct the transaction result')
            self._local.connection.execute(
                'UPDATE world_snapshots SET record_json=? WHERE world_id=?',
                (self._dump_record(snapshot), world_id))
            return response

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

    def note_global(self, request_id, entry):
        with self.locked():
            self._local.connection.execute(
                'INSERT INTO world_creations VALUES(?,?,?,?)',
                (request_id, entry['data']['worldId'], entry['digest'],
                 wire(dict(data=entry['data'], views=entry['views']))))
            self._local.connection.execute(
                'INSERT INTO world_creation_replays VALUES(?,?)', (request_id, _dump(entry)))
