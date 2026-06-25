"""Repository for campaign_progress table — replaces raw SQL in route handlers."""

import json

from app.database import Database


class CampaignProgressRepository:
    """Encapsulates all campaign_progress SQL that was previously inline in routes."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_slots(self, session_id: str | None = None) -> list[dict]:
        """List save slots, optionally filtered by session_id."""
        where_clause = ""
        params: tuple[str, ...] = ()
        if session_id:
            where_clause = "WHERE campaign_progress.campaign_id = ?"
            params = (session_id,)

        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT
                     campaign_progress.id,
                     campaign_progress.campaign_id,
                     campaign_progress.slot_name,
                     campaign_progress.arc_index,
                     campaign_progress.session_index,
                     campaign_progress.turn_in_session,
                     campaign_progress.updated_at,
                     game_sessions.campaign_filename,
                     game_sessions.active_slot_name
                   FROM campaign_progress
                   JOIN game_sessions ON game_sessions.id = campaign_progress.campaign_id
                   {where_clause}
                   ORDER BY campaign_progress.updated_at DESC""",
                params,
            ).fetchall()

        return [
            {
                "id": row["id"],
                "campaign_id": row["campaign_id"],
                "slot_name": row["slot_name"],
                "arc_index": row["arc_index"],
                "session_index": row["session_index"],
                "turn_in_session": row["turn_in_session"],
                "last_played": row["updated_at"],
                "campaign_filename": row["campaign_filename"],
                "is_active": row["slot_name"] == row["active_slot_name"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_slot(
        self,
        session_row: dict,
        slot_name: str,
        source_slot_name: str,
    ) -> dict:
        """Create a new save slot by copying from *source_slot_name*."""
        import re

        if not re.match(r"^[a-zA-Z0-9_一-鿿]+$", slot_name):
            raise ValueError("slot_name contains invalid characters")

        session_id = session_row["id"]
        campaign_id = session_row["campaign_id"] or session_id

        if self.db.read_campaign_progress(campaign_id, slot_name):
            raise ValueError(f"Slot '{slot_name}' already exists")

        source = self.db.read_campaign_progress(campaign_id, source_slot_name) or {}
        self.db.write_campaign_progress(
            campaign_id=campaign_id,
            slot_name=slot_name,
            arc_index=int(source.get("arc_index", 0)),
            session_index=int(source.get("session_index", 0)),
            turn_in_session=int(source.get("turn_in_session", 0)),
            fsm_state=str(source.get("fsm_state", "active/session_active")),
            revealed_anchors=json.loads(source.get("revealed_anchors", "[]")) if source else [],
            completed_arcs=json.loads(source.get("completed_arcs", "[]")) if source else [],
            recap_compressed=str(source.get("recap_compressed", "")),
            recap_full=str(source.get("recap_full", "")),
        )
        if source.get("npc_relations"):
            self.db.update_npc_relations(campaign_id, source["npc_relations"], slot_name)
        self.db.set_session_active_slot(session_id, slot_name)

        return {"status": "created", "slot_name": slot_name, "campaign_id": campaign_id}

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_slot(self, slot_name: str) -> bool:
        """Delete a slot by name. Returns True if a row was deleted."""
        with self.db.connect() as conn:
            result = conn.execute(
                "DELETE FROM campaign_progress WHERE slot_name = ?",
                (slot_name,),
            )
        return result.rowcount > 0
