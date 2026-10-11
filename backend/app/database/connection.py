"""Database core: connection management and schema bootstrap."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.database.campaign_store import CampaignStoreMixin
from app.database.knowledge_store import KnowledgeStoreMixin
from app.database.outputs import ModelOutputStoreMixin
from app.database.schema import init_schema
from app.database.sessions import SessionStoreMixin
from app.database.timeline import TimelineStoreMixin


class Database(
    SessionStoreMixin,
    CampaignStoreMixin,
    KnowledgeStoreMixin,
    ModelOutputStoreMixin,
    TimelineStoreMixin,
):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA cache_size = -2000")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @contextmanager
    def maybe_owned_connection(
        self, conn: sqlite3.Connection | None
    ) -> Iterator[sqlite3.Connection]:
        """Yield a caller-owned connection as-is, or open+commit one.

        The commit-turn flow runs every write of one submission on a single
        connection so a mid-flow failure rolls back together (design/
        component-io-and-commit-turn.md §4). Methods that accept a ``conn``
        parameter delegate their transaction boundaries to the caller; the
        default path keeps opening its own transaction.
        """
        if conn is not None:
            yield conn
            return
        with self.connect() as owned:
            yield owned

    @contextmanager
    def write_transaction(self) -> Iterator[sqlite3.Connection]:
        """One explicit write transaction on a fresh connection.

        BEGIN IMMEDIATE up front: concurrent same-requestId submissions
        serialize on the database lock, so the loser's idempotency lookup
        sees the winner's committed row instead of racing past it.
        """
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA cache_size = -2000")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self.connect() as db:
            init_schema(db)
