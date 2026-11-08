"""Crash-durable capture journal and a shared, preflight budget ledger.

No environment variables or credentials are read by this module.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import uuid


class CaptureBoundaryError(BaseException):
    """Fatal evaluation boundary: must bypass application fallback handlers."""


class MissingCapture(CaptureBoundaryError):
    pass


class UncertainCapture(CaptureBoundaryError):
    pass


class BudgetExceeded(CaptureBoundaryError):
    pass


_SECRET_KEYS = re.compile(r"(^|[_-])(api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token)($|[_-])", re.I)


def clean(value, secrets=()):
    """Strip credential fields, and known authorization values from error text."""
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if _SECRET_KEYS.search(str(k)) else clean(v, secrets)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return re.sub(r"(?i)\bBearer\s+[^\s\"'<>]+", "Bearer [REDACTED]", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return clean(str(value), secrets)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class _Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA busy_timeout=30000")

    @contextmanager
    def transaction(self):
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.db
            except BaseException:
                self.db.rollback()
                raise
            else:
                self.db.commit()

    def close(self):
        with self._lock:
            self.db.close()


class CallJournal(_Store):
    """One game journal; every request, response chunk and event commits durably."""
    def __init__(self, path):
        super().__init__(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS calls (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL, request_sha256 TEXT NOT NULL,
                request TEXT NOT NULL, context TEXT NOT NULL,
                response TEXT, error TEXT, budget_id TEXT,
                started_at TEXT NOT NULL, finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS capture_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL
            );
        """)
        self.db.commit()

    def start(self, request, context, budget_id=None):
        with self.transaction() as db:
            cursor = db.execute("INSERT INTO calls(status,request_sha256,request,context,budget_id,started_at) VALUES('pending',?,?,?,?,?)",
                                (fingerprint(request), encode(request), encode(clean(context)), budget_id, now()))
            return cursor.lastrowid

    def finish(self, sequence, response, status="complete"):
        with self.transaction() as db:
            changed = db.execute("UPDATE calls SET status=?,response=?,finished_at=? WHERE sequence=? AND status='pending'",
                                 (status, encode(response), now(), sequence)).rowcount
            if changed != 1:
                raise UncertainCapture("Cannot complete a non-pending capture: %s" % sequence)

    def fail(self, sequence, error):
        with self.transaction() as db:
            changed = db.execute("UPDATE calls SET status='error',error=?,finished_at=? WHERE sequence=? AND status='pending'",
                                 (encode(clean(error)), now(), sequence)).rowcount
            if changed != 1:
                raise UncertainCapture("Cannot fail a non-pending capture: %s" % sequence)

    def event(self, kind, payload):
        with self.transaction() as db:
            cursor = db.execute("INSERT INTO capture_events(created_at,kind,payload) VALUES(?,?,?)",
                                (now(), str(kind), encode(clean(payload))))
            return cursor.lastrowid

    def records(self, operation_id=None):
        with self._lock:
            rows = [dict(row) for row in self.db.execute("SELECT * FROM calls ORDER BY sequence")]
        for row in rows:
            for key in ("request", "context", "response", "error"):
                row[key] = json.loads(row[key]) if row[key] is not None else None
        if operation_id is not None:
            rows = [r for r in rows if r["context"].get("operation_id") == operation_id]
        return rows

    def events(self):
        with self._lock:
            return [{**dict(row), "payload": json.loads(row["payload"])}
                    for row in self.db.execute("SELECT * FROM capture_events ORDER BY sequence")]

    def stats(self):
        records = self.records()
        purposes, statuses = {}, {}
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "unknown_usage": 0}
        for row in records:
            purpose = row["context"].get("purpose", "unclassified")
            purposes[purpose] = purposes.get(purpose, 0) + 1
            statuses[row["status"]] = statuses.get(row["status"], 0) + 1
            measured = (row.get("response") or {}).get("usage")
            if measured is None:
                usage["unknown_usage"] += 1
            else:
                usage["input_tokens"] += measured.get("prompt_tokens", measured.get("input_tokens", 0)) or 0
                usage["output_tokens"] += measured.get("completion_tokens", measured.get("output_tokens", 0)) or 0
                usage["total_tokens"] += measured.get("total_tokens", 0) or 0
        repeats = {}
        sdk_retries = 0
        for row in records:
            key = (row["context"].get("operation_id"), row["request_sha256"])
            repeats[key] = repeats.get(key, 0) + 1
            retry_index = row["request"].get("sdk_retry_index")
            try:
                sdk_retries += int(retry_index) > 0
            except (TypeError, ValueError):
                pass
        return {"attempts": len(records), "statuses": statuses, "purposes": purposes,
                "repeated_request_attempts": sdk_retries,
                "sdk_retry_attempts": sdk_retries,
                "identical_request_repetitions": sum(max(0, n - 1) for n in repeats.values()), **usage}


class BudgetLedger(_Store):
    """Global run budget; reservations survive crashes and concurrent workers.

    limits: max_attempts, max_input_tokens, max_output_tokens, max_cost_usd;
    optional max_unpriced_attempts explicitly permits otherwise-unpriced calls.
    prices: {model: {input_per_million, output_per_million}} in USD.
    Unknown usage retains the entire reservation. Costs are conservative estimates,
    not invoice totals. Cache discounts are deliberately not assumed.
    """
    def __init__(self, path, limits, prices):
        super().__init__(path)
        self.limits, self.prices = clean(dict(limits)), clean(dict(prices))
        for key in ("max_attempts", "max_input_tokens", "max_output_tokens"):
            if type(self.limits.get(key)) is not int or self.limits[key] < 1:
                raise ValueError("Positive integer required: " + key)
        if self.limits.get("max_cost_usd") is not None and self.limits["max_cost_usd"] <= 0:
            raise ValueError("max_cost_usd must be positive")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS budget_config (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS budget_control (id INTEGER PRIMARY KEY CHECK(id=1), stop_reason TEXT);
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY, model TEXT NOT NULL, context TEXT NOT NULL,
                input_reserved INTEGER NOT NULL, output_reserved INTEGER NOT NULL,
                cost_reserved REAL NOT NULL, unpriced INTEGER NOT NULL,
                input_actual INTEGER, output_actual INTEGER, cost_actual REAL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT
            );
        """)
        self.db.commit()
        expected = encode({"limits": self.limits, "prices": self.prices})
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO budget_control VALUES(1,NULL)")
            old = db.execute("SELECT value FROM budget_config WHERE id=1").fetchone()
            if old and old[0] != expected:
                raise BudgetExceeded("Budget limits or prices changed; refusing to resume the same ledger")
            if not old:
                db.execute("INSERT INTO budget_config VALUES(1,?)", (expected,))

    def _stats(self, db, game_id=None):
        query = """SELECT COUNT(*) attempts,
            COALESCE(SUM(COALESCE(input_actual,input_reserved)),0) input_tokens,
            COALESCE(SUM(COALESCE(output_actual,output_reserved)),0) output_tokens,
            COALESCE(SUM(COALESCE(cost_actual,cost_reserved)),0) cost_usd,
            COALESCE(SUM(input_actual),0) actual_input_tokens,
            COALESCE(SUM(output_actual),0) actual_output_tokens,
            COALESCE(SUM(cost_actual),0) known_usage_cost_usd,
            COALESCE(SUM(unpriced),0) unpriced_attempts,
            COALESCE(SUM(status='reserved'),0) outstanding_reservations,
            COALESCE(SUM(status='unknown'),0) unknown_usage
            FROM reservations"""
        params = ()
        if game_id is not None:
            query += " WHERE json_extract(context,'$.game_id')=?"
            params = (game_id,)
        row = db.execute(query, params).fetchone()
        return dict(row)

    def stats(self, game_id=None):
        with self._lock:
            result = self._stats(self.db, game_id)
            stopped = self.db.execute("SELECT stop_reason FROM budget_control WHERE id=1").fetchone()[0]
        return {**result, "limits": self.limits, "prices": self.prices,
                "stopped": stopped is not None, "stop_reason": stopped,
                "cost_basis": "conservative published-rate estimate; unpriced calls have unknown cost"}

    def reserve(self, body, context=None):
        if not isinstance(body, dict):
            raise BudgetExceeded("Cannot budget a non-JSON model request")
        model = body.get("model")
        if not isinstance(model, str):
            raise BudgetExceeded("Cannot budget a model request without model")
        is_embedding = "input" in body and "messages" not in body
        output = 0 if is_embedding else body.get("max_completion_tokens", body.get("max_tokens"))
        if type(output) is not int or output < 0:
            raise BudgetExceeded("A finite max_tokens is required before a paid request")
        # A UTF-8 byte bound avoids tokenization downloads or an unrecorded API.
        # Include all request fields plus overhead, not only message content.
        input_bound = len(encode(body).encode("utf-8")) + 256
        price = self.prices.get(model)
        unpriced = not isinstance(price, dict)
        cost = 0.0 if unpriced else (input_bound * float(price["input_per_million"]) + output * float(price["output_per_million"])) / 1_000_000
        reservation_id = uuid.uuid4().hex
        with self.transaction() as db:
            stopped = db.execute("SELECT stop_reason FROM budget_control WHERE id=1").fetchone()[0]
            if stopped:
                raise BudgetExceeded(stopped)
            stats = self._stats(db)
            checks = (("max_attempts", stats["attempts"] + 1),
                      ("max_input_tokens", stats["input_tokens"] + input_bound),
                      ("max_output_tokens", stats["output_tokens"] + output))
            for limit, value in checks:
                if value > self.limits[limit]:
                    raise BudgetExceeded("Budget stopped before request: " + limit)
            if unpriced and stats["unpriced_attempts"] + 1 > self.limits.get("max_unpriced_attempts", 0):
                raise BudgetExceeded("Unpriced request not authorized: " + model)
            ceiling = self.limits.get("max_cost_usd")
            if ceiling is not None and stats["cost_usd"] + cost > ceiling + 1e-12:
                raise BudgetExceeded("Budget stopped before request: max_cost_usd")
            db.execute("INSERT INTO reservations VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,'reserved',?,NULL)",
                       (reservation_id, model, encode(clean(context or {})), input_bound, output, cost, int(unpriced), now()))
        return reservation_id

    def settle(self, reservation_id, usage=None):
        stop_reason = None
        with self.transaction() as db:
            stopped = db.execute("SELECT stop_reason FROM budget_control WHERE id=1").fetchone()[0]
            if stopped:
                raise BudgetExceeded(stopped)
            row = db.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
            if row is None:
                raise UncertainCapture("Unknown budget reservation")
            if row["status"] != "reserved":
                return
            input_actual = (usage or {}).get("prompt_tokens", (usage or {}).get("input_tokens"))
            output_actual = (usage or {}).get("completion_tokens", (usage or {}).get("output_tokens"))
            if output_actual is None and row["output_reserved"] == 0:
                output_actual = 0
            known = type(input_actual) is int and input_actual >= 0 and type(output_actual) is int and output_actual >= 0
            price = self.prices.get(row["model"])
            cost_actual = ((input_actual * float(price["input_per_million"]) + output_actual * float(price["output_per_million"])) / 1_000_000) if known and price else None
            db.execute("UPDATE reservations SET input_actual=?,output_actual=?,cost_actual=?,status=?,finished_at=? WHERE id=?",
                       (input_actual if known else None, output_actual if known else None, cost_actual,
                        "settled" if known else "unknown", now(), reservation_id))
            if known and (input_actual > row["input_reserved"] or output_actual > row["output_reserved"]):
                stop_reason = "Provider usage exceeded preflight bounds; actual usage saved and budget permanently stopped"
                db.execute("UPDATE budget_control SET stop_reason=? WHERE id=1", (stop_reason,))
        # Do not raise inside the transaction: both actual usage and the durable
        # stop must survive the exception and process restart.
        if stop_reason:
            raise BudgetExceeded(stop_reason)
