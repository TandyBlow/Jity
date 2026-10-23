"""In-memory fixture baseline store: the A2 service's authoritative state.

A process-wide RLock serialises every world transaction; each transaction
mutates a deep copy and commits by an atomic reference swap, so a refused
operation never leaves partial work, versions or idempotency rows. Storage
keeps the server-authoritative record only — blockedReasons/canCompute are
derived per response, never stored. SQLite persistence, TTL clocks, takeover
copying and crash recovery stay with A3 (SQLiteBaselineStore).
"""
import copy
import threading

_LOCK = threading.RLock()

NARRATION_STATUSES = ('pending', 'ready', 'failed', 'missing')


class FixtureBaselineStore:
    def __init__(self, clock=None):
        self._worlds = {}
        self._sequence = 0
        self._idempotency_global = {}
        self._clock = clock or (lambda: 1_792_617_600_000)

    def clock_milli(self):
        return int(self._clock())

    def next_id(self, kind):
        with _LOCK:
            self._sequence += 1
            return f'{kind}_{self._sequence}'

    def create_world(self, world_id, record):
        with _LOCK:
            if world_id in self._worlds:
                raise KeyError(world_id)
            self._worlds[world_id] = record

    def world(self, world_id):
        with _LOCK:
            record = self._worlds.get(world_id)
            return copy.deepcopy(record) if record is not None else None

    def transact(self, world_id, handler):
        """Run handler(record_copy) -> response payload on a deep copy and
        commit by swap; any exception discards the copy."""
        with _LOCK:
            record = self._worlds.get(world_id)
            snapshot = copy.deepcopy(record)
            response = handler(snapshot)
            self._worlds[world_id] = snapshot
            return response

    def global_idempotency(self):
        with _LOCK:
            return self._idempotency_global

    def note_global(self, request_id, entry):
        with _LOCK:
            self._idempotency_global[request_id] = entry
