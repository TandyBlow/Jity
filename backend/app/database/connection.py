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


class Database(
    SessionStoreMixin,
    CampaignStoreMixin,
    KnowledgeStoreMixin,
    ModelOutputStoreMixin,
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

    def _init_schema(self) -> None:
        with self.connect() as db:
            init_schema(db)
