"""CampaignPersistence — DB read/write for campaign_progress rows + NPC decay."""

import json
import logging

from app.database import Database

logger = logging.getLogger(__name__)


class CampaignPersistence:
    """Encapsulates all campaign_progress DB persistence.

    Extracted from CampaignManager to isolate the persistence concern.
    Takes campaign_id and slot_name as method arguments so it remains
    stateless with respect to the current session.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # ── Write ────────────────────────────────────────────────────────

    def save(
        self,
        campaign_id: str,
        slot_name: str,
        arc_index: int,
        session_index: int,
        turn_in_session: int,
        fsm_state: str,
        revealed_anchors: list[str],
        completed_arcs: list[int],
    ) -> None:
        """Persist progress row preserving existing recap fields."""
        recap_compressed, recap_full = self._current_recap_fields(campaign_id, slot_name)
        self.db.write_campaign_progress(
            campaign_id=campaign_id,
            arc_index=arc_index,
            session_index=session_index,
            turn_in_session=turn_in_session,
            fsm_state=fsm_state,
            revealed_anchors=revealed_anchors,
            completed_arcs=completed_arcs,
            recap_compressed=recap_compressed,
            recap_full=recap_full,
            slot_name=slot_name,
        )

    def save_with_recap(
        self,
        campaign_id: str,
        slot_name: str,
        arc_index: int,
        session_index: int,
        turn_in_session: int,
        fsm_state: str,
        revealed_anchors: list[str],
        completed_arcs: list[int],
        recap_compressed: str,
        recap_full: str,
    ) -> None:
        """Persist progress row with explicit recap field values."""
        self.db.write_campaign_progress(
            campaign_id=campaign_id,
            arc_index=arc_index,
            session_index=session_index,
            turn_in_session=turn_in_session,
            fsm_state=fsm_state,
            revealed_anchors=revealed_anchors,
            completed_arcs=completed_arcs,
            recap_compressed=recap_compressed,
            recap_full=recap_full,
            slot_name=slot_name,
        )

    # ── Read ─────────────────────────────────────────────────────────

    def load(self, campaign_id: str, slot_name: str) -> dict | None:
        """Return the raw progress row dict, or None."""
        return self.db.read_campaign_progress(campaign_id, slot_name)

    def read_recap_compressed(self, campaign_id: str, slot_name: str) -> str:
        """Read compressed recap field, or empty string."""
        row = self.db.read_campaign_progress(campaign_id, slot_name)
        if row:
            return row.get("recap_compressed", "")
        return ""

    # ── NPC relations ────────────────────────────────────────────────

    def decay_npc_relations(self, campaign_id: str, slot_name: str) -> None:
        """Decay all NPC affinities toward 0 by 1 at session boundary."""
        row = self.db.read_campaign_progress(campaign_id, slot_name)
        if not row:
            return
        try:
            relations = json.loads(row.get("npc_relations", "[]"))
            for r in relations:
                current = r.get("affinity", 0)
                if current > 0:
                    r["affinity"] = max(current - 1, 0)
                elif current < 0:
                    r["affinity"] = min(current + 1, 0)
            self.db.update_npc_relations(
                campaign_id,
                json.dumps(relations, ensure_ascii=False),
                slot_name,
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("NPC relations decode failed for campaign %s", campaign_id)

    # ── Private ──────────────────────────────────────────────────────

    def _current_recap_fields(self, campaign_id: str, slot_name: str) -> tuple[str, str]:
        """Preserve existing recap fields when writing unrelated progress."""
        row = self.db.read_campaign_progress(campaign_id, slot_name)
        if not isinstance(row, dict):
            return "", ""
        return row.get("recap_compressed", ""), row.get("recap_full", "")
