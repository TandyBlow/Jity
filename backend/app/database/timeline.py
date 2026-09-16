"""Branching story timeline persistence."""

import json
from typing import Any


class TimelineStoreMixin:
    def ensure_timeline_root(
        self,
        session_id: str,
        state: dict[str, Any],
        model: str,
        campaign_progress: dict[str, Any] | None = None,
    ) -> int:
        """Create and activate the immutable root snapshot for a new session."""
        with self.connect() as db:
            row = db.execute(
                "SELECT active_turn_id FROM game_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row and row["active_turn_id"]:
                return int(row["active_turn_id"])
            cursor = db.execute(
                """
                INSERT INTO story_turns
                  (session_id, parent_turn_id, depth, player_action, output_json,
                   state_json, campaign_progress_json, model, source)
                VALUES (?, NULL, 0, '', NULL, ?, ?, ?, 'scripted')
                """,
                (
                    session_id,
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(campaign_progress or {}, ensure_ascii=False),
                    model,
                ),
            )
            root_id = int(cursor.lastrowid)
            db.execute(
                "UPDATE game_sessions SET active_turn_id = ? WHERE id = ?",
                (root_id, session_id),
            )
            return root_id

    def update_active_turn_snapshot(
        self,
        session_id: str,
        state: dict[str, Any],
        campaign_progress: dict[str, Any] | None = None,
    ) -> None:
        """Refresh the active root while a session is still being initialized."""
        with self.connect() as db:
            db.execute(
                """
                UPDATE story_turns
                SET state_json = ?, campaign_progress_json = ?
                WHERE id = (SELECT active_turn_id FROM game_sessions WHERE id = ?)
                  AND parent_turn_id IS NULL
                """,
                (
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(campaign_progress or {}, ensure_ascii=False),
                    session_id,
                ),
            )

    def get_active_turn_id(self, session_id: str) -> int | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT active_turn_id FROM game_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return int(row["active_turn_id"]) if row and row["active_turn_id"] else None

    def get_story_turn(self, session_id: str, turn_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM story_turns WHERE id = ? AND session_id = ?",
                (turn_id, session_id),
            ).fetchone()
        return dict(row) if row else None

    def list_story_turns(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT id, parent_turn_id, depth, player_action, output_json,
                       state_json, source, model, created_at
                FROM story_turns
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def commit_story_turn(
        self,
        *,
        session_id: str,
        expected_parent_id: int,
        player_action: str,
        output: dict[str, Any],
        state: dict[str, Any],
        campaign_progress: dict[str, Any] | None,
        model: str,
        source: str,
        model_output_id: int | None,
        campaign_session_index: int = 0,
    ) -> int:
        """Append a child and atomically move the session head to it."""
        from app.exceptions import ConcurrentModificationError

        with self.connect() as db:
            parent = db.execute(
                "SELECT depth FROM story_turns WHERE id = ? AND session_id = ?",
                (expected_parent_id, session_id),
            ).fetchone()
            current = db.execute(
                "SELECT active_turn_id FROM game_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not parent or not current or current["active_turn_id"] != expected_parent_id:
                raise ConcurrentModificationError(
                    f"Timeline head changed for session {session_id}"
                )

            cursor = db.execute(
                """
                INSERT INTO story_turns
                  (session_id, parent_turn_id, depth, player_action, output_json,
                   state_json, campaign_progress_json, model, source, model_output_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    expected_parent_id,
                    int(parent["depth"]) + 1,
                    player_action,
                    json.dumps(output, ensure_ascii=False),
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(campaign_progress or {}, ensure_ascii=False),
                    model,
                    source,
                    model_output_id,
                ),
            )
            turn_id = int(cursor.lastrowid)
            progress = campaign_progress or {}
            if progress:
                db.execute(
                    """
                    INSERT INTO campaign_progress
                      (campaign_id, slot_name, arc_index, session_index, turn_in_session,
                       fsm_state, revealed_anchors, completed_arcs, recap_compressed,
                       recap_full, npc_relations, head_turn_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campaign_id, slot_name) DO UPDATE SET
                      arc_index = excluded.arc_index,
                      session_index = excluded.session_index,
                      turn_in_session = excluded.turn_in_session,
                      fsm_state = excluded.fsm_state,
                      revealed_anchors = excluded.revealed_anchors,
                      completed_arcs = excluded.completed_arcs,
                      recap_compressed = excluded.recap_compressed,
                      recap_full = excluded.recap_full,
                      npc_relations = excluded.npc_relations,
                      head_turn_id = excluded.head_turn_id,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        progress.get("campaign_id", session_id),
                        str(progress.get("slot_name") or "default"),
                        int(progress.get("arc_index", 0)),
                        int(progress.get("session_index", 0)),
                        int(progress.get("turn_in_session", 0)),
                        str(progress.get("fsm_state", "active/session_active")),
                        progress.get("revealed_anchors", "[]"),
                        progress.get("completed_arcs", "[]"),
                        str(progress.get("recap_compressed", "")),
                        str(progress.get("recap_full", "")),
                        progress.get("npc_relations", "[]"),
                        turn_id,
                    ),
                )
            db.execute(
                """
                INSERT INTO session_messages
                  (session_id, role, content, campaign_session_index, turn_node_id)
                VALUES (?, 'user', ?, ?, ?), (?, 'assistant', ?, ?, ?)
                """,
                (
                    session_id,
                    player_action,
                    campaign_session_index,
                    turn_id,
                    session_id,
                    json.dumps(output, ensure_ascii=False),
                    campaign_session_index,
                    turn_id,
                ),
            )
            updated = db.execute(
                """
                UPDATE game_sessions
                SET state_json = ?, model = ?, active_turn_id = ?,
                    version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND active_turn_id = ?
                """,
                (
                    json.dumps(state, ensure_ascii=False),
                    model,
                    turn_id,
                    session_id,
                    expected_parent_id,
                ),
            )
            if updated.rowcount != 1:
                raise ConcurrentModificationError(
                    f"Timeline head changed for session {session_id}"
                )
            return turn_id

    def activate_story_turn(self, session_id: str, turn_id: int) -> dict[str, Any] | None:
        """Restore a node snapshot without removing any descendants."""
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM story_turns WHERE id = ? AND session_id = ?",
                (turn_id, session_id),
            ).fetchone()
            if not row:
                return None
            snapshot = dict(row)
            state = json.loads(snapshot["state_json"])
            progress = json.loads(snapshot["campaign_progress_json"] or "{}")
            slot_name = str(progress.get("slot_name") or "default")

            db.execute(
                """
                UPDATE game_sessions
                SET state_json = ?, model = ?, active_turn_id = ?, active_slot_name = ?,
                    version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (snapshot["state_json"], snapshot["model"], turn_id, slot_name, session_id),
            )
            if progress:
                db.execute(
                    """
                    INSERT INTO campaign_progress
                      (campaign_id, slot_name, arc_index, session_index, turn_in_session,
                       fsm_state, revealed_anchors, completed_arcs, recap_compressed,
                       recap_full, npc_relations, head_turn_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campaign_id, slot_name) DO UPDATE SET
                      arc_index = excluded.arc_index,
                      session_index = excluded.session_index,
                      turn_in_session = excluded.turn_in_session,
                      fsm_state = excluded.fsm_state,
                      revealed_anchors = excluded.revealed_anchors,
                      completed_arcs = excluded.completed_arcs,
                      recap_compressed = excluded.recap_compressed,
                      recap_full = excluded.recap_full,
                      npc_relations = excluded.npc_relations,
                      head_turn_id = excluded.head_turn_id,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        progress.get("campaign_id", session_id),
                        slot_name,
                        int(progress.get("arc_index", 0)),
                        int(progress.get("session_index", 0)),
                        int(progress.get("turn_in_session", 0)),
                        str(progress.get("fsm_state", "active/session_active")),
                        progress.get("revealed_anchors", "[]"),
                        progress.get("completed_arcs", "[]"),
                        str(progress.get("recap_compressed", "")),
                        str(progress.get("recap_full", "")),
                        progress.get("npc_relations", "[]"),
                        turn_id,
                    ),
                )
        snapshot["state"] = state
        snapshot["campaign_progress"] = progress
        snapshot["output"] = json.loads(snapshot["output_json"]) if snapshot["output_json"] else None
        return snapshot
