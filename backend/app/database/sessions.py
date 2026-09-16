"""Session and message persistence."""

import json
import sqlite3
from typing import Any


class SessionStoreMixin:
    def set_session_campaign_id(
        self,
        session_id: str,
        campaign_id: str,
        campaign_filename: str | None = None,
        active_slot_name: str = "default",
    ) -> None:
        """Set campaign metadata on a game session row."""
        with self.connect() as db:
            db.execute(
                """
                UPDATE game_sessions
                SET campaign_id = ?,
                    campaign_filename = COALESCE(?, campaign_filename),
                    active_slot_name = ?
                WHERE id = ?
                """,
                (campaign_id, campaign_filename, active_slot_name, session_id),
            )

    def set_session_active_slot(self, session_id: str, slot_name: str) -> None:
        """Remember which campaign progress slot should drive future turns."""
        with self.connect() as db:
            db.execute(
                "UPDATE game_sessions SET active_slot_name = ? WHERE id = ?",
                (slot_name, session_id),
            )

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

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        campaign_session_index: int = 0,
        turn_node_id: int | None = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO session_messages
                   (session_id, role, content, campaign_session_index, turn_node_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, role, content, campaign_session_index, turn_node_id),
            )

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                WITH RECURSIVE lineage(id) AS (
                  SELECT active_turn_id FROM game_sessions WHERE id = ?
                  UNION ALL
                  SELECT story_turns.parent_turn_id
                  FROM story_turns JOIN lineage ON story_turns.id = lineage.id
                  WHERE story_turns.parent_turn_id IS NOT NULL
                )
                SELECT id, role, content, created_at
                FROM session_messages
                WHERE session_id = ?
                  AND (turn_node_id IN (SELECT id FROM lineage) OR turn_node_id IS NULL)
                ORDER BY id ASC
                """,
                (session_id, session_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_recent_messages(
        self,
        session_id: str,
        limit: int = 10,
        campaign_session_index: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent branch messages, optionally scoped to one campaign session."""
        with self.connect() as db:
            rows = db.execute(
                """
                WITH RECURSIVE lineage(id) AS (
                  SELECT active_turn_id FROM game_sessions WHERE id = ?
                  UNION ALL
                  SELECT story_turns.parent_turn_id
                  FROM story_turns JOIN lineage ON story_turns.id = lineage.id
                  WHERE story_turns.parent_turn_id IS NOT NULL
                )
                SELECT id, role, content, campaign_session_index, created_at
                FROM session_messages
                WHERE session_id = ? AND role IN ('user', 'assistant')
                  AND (turn_node_id IN (SELECT id FROM lineage) OR turn_node_id IS NULL)
                  AND (? IS NULL OR campaign_session_index = ?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (
                    session_id,
                    session_id,
                    campaign_session_index,
                    campaign_session_index,
                    limit,
                ),
            ).fetchall()
            return [dict(row) for row in reversed(rows)]
