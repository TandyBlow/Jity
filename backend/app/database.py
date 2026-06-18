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
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS game_sessions (
                  id TEXT PRIMARY KEY,
                  game_name TEXT NOT NULL,
                  model TEXT NOT NULL,
                  state_json TEXT NOT NULL,
                  version INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS campaign_progress (
                  campaign_id TEXT PRIMARY KEY,
                  arc_index INTEGER NOT NULL DEFAULT 0,
                  session_index INTEGER NOT NULL DEFAULT 0,
                  turn_in_session INTEGER NOT NULL DEFAULT 0,
                  fsm_state TEXT NOT NULL DEFAULT 'idle',
                  revealed_anchors TEXT NOT NULL DEFAULT '[]',
                  completed_arcs TEXT NOT NULL DEFAULT '[]',
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
                  importance INTEGER NOT NULL DEFAULT 3,
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
                  retrieved_chunks_json TEXT NOT NULL DEFAULT '[]',
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
            self._ensure_column(db, "model_outputs", "retrieved_chunks_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "knowledge_chunks", "importance", "INTEGER NOT NULL DEFAULT 3")
            self._ensure_column(db, "game_sessions", "version", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "model_outputs", "word_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "model_outputs", "option_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "model_outputs", "sanity_delta", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "model_outputs", "health_delta", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "model_outputs", "dialogue_lines", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "model_outputs", "location_changed", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "model_outputs", "token_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "campaign_progress", "recap_compressed", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "campaign_progress", "recap_full", "TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def write_session(
        self,
        session_id: str,
        game_name: str,
        model: str,
        state: dict[str, Any],
        expected_version: int | None = None,
    ) -> int:
        """Persist game state with optional optimistic locking.

        Returns the new version number.
        Raises ConcurrentModificationError if expected_version doesn't match.
        """
        from app.exceptions import ConcurrentModificationError

        with self.connect() as db:
            if expected_version is not None:
                cursor = db.execute(
                    """
                    UPDATE game_sessions
                    SET game_name = ?,
                        model = ?,
                        state_json = ?,
                        version = version + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND version = ?
                    """,
                    (
                        game_name,
                        model,
                        json.dumps(state, ensure_ascii=False),
                        session_id,
                        expected_version,
                    ),
                )
                if cursor.rowcount == 0:
                    raise ConcurrentModificationError(
                        f"State version mismatch for session {session_id}. "
                        f"Expected version {expected_version}, but row was already updated."
                    )
                return expected_version + 1
            else:
                db.execute(
                    """
                    INSERT INTO game_sessions (id, game_name, model, state_json, version)
                    VALUES (?, ?, ?, ?, 0)
                    ON CONFLICT(id) DO UPDATE SET
                      game_name = excluded.game_name,
                      model = excluded.model,
                      state_json = excluded.state_json,
                      version = game_sessions.version + 1,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (session_id, game_name, model, json.dumps(state, ensure_ascii=False)),
                )
                row = db.execute(
                    "SELECT version FROM game_sessions WHERE id = ?", (session_id,)
                ).fetchone()
                return row["version"] if row else 0

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

    def read_campaign_progress(self, campaign_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM campaign_progress WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def write_campaign_progress(self, campaign_id: str, arc_index: int, session_index: int, turn_in_session: int, fsm_state: str, revealed_anchors: list[str] | None = None, completed_arcs: list[int] | None = None, recap_compressed: str = "", recap_full: str = "") -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO campaign_progress
                  (campaign_id, arc_index, session_index, turn_in_session, fsm_state, revealed_anchors, completed_arcs, recap_compressed, recap_full)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_id) DO UPDATE SET
                  arc_index = excluded.arc_index,
                  session_index = excluded.session_index,
                  turn_in_session = excluded.turn_in_session,
                  fsm_state = excluded.fsm_state,
                  revealed_anchors = excluded.revealed_anchors,
                  completed_arcs = excluded.completed_arcs,
                  recap_compressed = excluded.recap_compressed,
                  recap_full = excluded.recap_full,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (
                    campaign_id,
                    arc_index,
                    session_index,
                    turn_in_session,
                    fsm_state,
                    json.dumps(revealed_anchors or [], ensure_ascii=False),
                    json.dumps(completed_arcs or [], ensure_ascii=False),
                    recap_compressed,
                    recap_full,
                ),
            )

    def replace_knowledge_chunks(self, chunks: list[dict[str, Any]]) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM knowledge_chunks")
            db.executemany(
                """
                INSERT INTO knowledge_chunks (id, source_type, title, content, keywords, importance, source_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk["id"],
                        chunk["source_type"],
                        chunk["title"],
                        chunk["content"],
                        json.dumps(chunk.get("keywords", []), ensure_ascii=False),
                        int(chunk.get("importance", 3)),
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
        retrieved_chunks: list[dict[str, Any]] | None = None,
        word_count: int = 0,
        option_count: int = 0,
        sanity_delta: int = 0,
        health_delta: int = 0,
        dialogue_lines: int = 0,
        location_changed: int = 0,
        token_count: int = 0,
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
                  error_text,
                  retrieved_chunks_json,
                  word_count,
                  option_count,
                  sanity_delta,
                  health_delta,
                  dialogue_lines,
                  location_changed,
                  token_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(retrieved_chunks or [], ensure_ascii=False),
                    word_count,
                    option_count,
                    sanity_delta,
                    health_delta,
                    dialogue_lines,
                    location_changed,
                    token_count,
                ),
            )
            return int(cursor.lastrowid)
