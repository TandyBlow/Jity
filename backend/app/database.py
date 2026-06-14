from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS game_sessions (
                  id TEXT PRIMARY KEY,
                  game_name TEXT NOT NULL,
                  model TEXT NOT NULL,
                  state_json TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS session_messages (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (session_id) REFERENCES game_sessions(id)
                );

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                  id TEXT PRIMARY KEY,
                  source_type TEXT NOT NULL,
                  title TEXT NOT NULL,
                  content TEXT NOT NULL,
                  keywords TEXT NOT NULL DEFAULT '[]',
                  source_path TEXT NOT NULL,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS model_outputs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  model TEXT NOT NULL,
                  input_text TEXT NOT NULL,
                  output_json TEXT NOT NULL,
                  latency_ms INTEGER NOT NULL DEFAULT 0,
                  source TEXT NOT NULL DEFAULT 'llm',
                  status TEXT NOT NULL DEFAULT 'ok',
                  raw_output_text TEXT NOT NULL DEFAULT '',
                  error_text TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (session_id) REFERENCES game_sessions(id)
                );

                CREATE TABLE IF NOT EXISTS evaluations (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  model_output_id INTEGER NOT NULL,
                  coherence INTEGER,
                  lore_consistency INTEGER,
                  npc_consistency INTEGER,
                  action_relevance INTEGER,
                  creativity INTEGER,
                  controllability INTEGER,
                  playability INTEGER,
                  notes TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (model_output_id) REFERENCES model_outputs(id)
                );
                """
            )
            self._ensure_column(db, "model_outputs", "source", "TEXT NOT NULL DEFAULT 'llm'")
            self._ensure_column(db, "model_outputs", "status", "TEXT NOT NULL DEFAULT 'ok'")
            self._ensure_column(db, "model_outputs", "raw_output_text", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "model_outputs", "error_text", "TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def write_session(self, session_id: str, game_name: str, model: str, state: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO game_sessions (id, game_name, model, state_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  game_name = excluded.game_name,
                  model = excluded.model,
                  state_json = excluded.state_json,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (session_id, game_name, model, json.dumps(state, ensure_ascii=False)),
            )

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute("SELECT * FROM game_sessions WHERE id = ?", (session_id,)).fetchone()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO session_messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT id, role, content, created_at
                FROM session_messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def replace_knowledge_chunks(self, chunks: list[dict[str, Any]]) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM knowledge_chunks")
            db.executemany(
                """
                INSERT INTO knowledge_chunks (id, source_type, title, content, keywords, source_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk["id"],
                        chunk["source_type"],
                        chunk["title"],
                        chunk["content"],
                        json.dumps(chunk.get("keywords", []), ensure_ascii=False),
                        chunk.get("source_path", ""),
                    )
                    for chunk in chunks
                ],
            )

    def add_model_output(
        self,
        session_id: str,
        model: str,
        input_text: str,
        output: dict[str, Any],
        latency_ms: int,
        source: str = "llm",
        status: str = "ok",
        raw_output_text: str = "",
        error_text: str = "",
    ) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO model_outputs (
                  session_id,
                  model,
                  input_text,
                  output_json,
                  latency_ms,
                  source,
                  status,
                  raw_output_text,
                  error_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    model,
                    input_text,
                    json.dumps(output, ensure_ascii=False),
                    latency_ms,
                    source,
                    status,
                    raw_output_text,
                    error_text,
                ),
            )
            return int(cursor.lastrowid)
