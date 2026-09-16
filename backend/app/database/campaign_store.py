"""Campaign progress persistence."""

import json
from typing import Any


class CampaignStoreMixin:
    def update_npc_relations(self, campaign_id: str, relations_json: str, slot_name: str = "default") -> None:
        """Update npc_relations JSON for a campaign progress row."""
        with self.connect() as db:
            db.execute(
                "UPDATE campaign_progress SET npc_relations = ?, updated_at = CURRENT_TIMESTAMP WHERE campaign_id = ? AND slot_name = ?",
                (relations_json, campaign_id, slot_name),
            )

    def read_campaign_progress(self, campaign_id: str, slot_name: str = "default") -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM campaign_progress WHERE campaign_id = ? AND slot_name = ?",
                (campaign_id, slot_name),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def read_campaign_progress_by_id(self, progress_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM campaign_progress WHERE id = ?",
                (progress_id,),
            ).fetchone()
            return dict(row) if row else None

    def write_campaign_progress(self, campaign_id: str, arc_index: int, session_index: int, turn_in_session: int, fsm_state: str, revealed_anchors: list[str] | None = None, completed_arcs: list[int] | None = None, recap_compressed: str = "", recap_full: str = "", slot_name: str = "default", head_turn_id: int | None = None) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO campaign_progress
                  (campaign_id, slot_name, arc_index, session_index, turn_in_session, fsm_state, revealed_anchors, completed_arcs, recap_compressed, recap_full, head_turn_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_id, slot_name) DO UPDATE SET
                  arc_index = excluded.arc_index,
                  session_index = excluded.session_index,
                  turn_in_session = excluded.turn_in_session,
                  fsm_state = excluded.fsm_state,
                  revealed_anchors = excluded.revealed_anchors,
                  completed_arcs = excluded.completed_arcs,
                  recap_compressed = excluded.recap_compressed,
                  recap_full = excluded.recap_full,
                  head_turn_id = COALESCE(excluded.head_turn_id, campaign_progress.head_turn_id),
                  updated_at = CURRENT_TIMESTAMP
                """,
                (
                    campaign_id,
                    slot_name,
                    arc_index,
                    session_index,
                    turn_in_session,
                    fsm_state,
                    json.dumps(revealed_anchors or [], ensure_ascii=False),
                    json.dumps(completed_arcs or [], ensure_ascii=False),
                    recap_compressed,
                    recap_full,
                    head_turn_id,
                ),
            )
