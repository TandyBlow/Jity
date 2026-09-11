"""CampaignLoader — load, version-check, migrate, validate campaign.json.

Extracted from CampaignManager to isolate the loading concern.
"""

import json
import logging
from pathlib import Path
from typing import Any

from app.database import Database
from app.schemas.campaign import (
    CampaignSchema,
    CampaignProgress,
    CURRENT_SCHEMA_VERSION,
    campaign_adapter,
    migrate,
)
from app.services.campaign_fsm import CampaignStateMachine
from app.services.campaign_persistence import CampaignPersistence

logger = logging.getLogger(__name__)


class CampaignLoader:
    """Loads campaign.json, runs migrations, validates schema, inits FSM + progress."""

    def __init__(self, db: Database, persistence: CampaignPersistence) -> None:
        self.db = db
        self.persistence = persistence

        # State set after load()
        self.campaign: CampaignSchema | None = None
        self.progress: CampaignProgress | None = None
        self.slot_name = "default"
        self.fsm = CampaignStateMachine()

    def load(
        self,
        campaign_path: Path,
        campaign_id: str | None = None,
        start_arc_index: int = 0,
        start_session_index: int = 0,
        slot_name: str = "default",
    ) -> CampaignSchema:
        """Load, version-check, migrate, validate campaign.json.

        Steps:
        1. Read JSON from campaign_path
        2. Check version field against CURRENT_SCHEMA_VERSION
        3. Run migration chain
        4. Validate against CampaignSchema via TypeAdapter
        5. Cache in self.campaign
        6. Init FSM and progress
        7. Return validated CampaignSchema

        Raises:
            FileNotFoundError: campaign_path does not exist
            ValueError: JSON parse error or schema validation failure
        """
        if not campaign_path.exists():
            raise FileNotFoundError(f"Campaign file not found: {campaign_path}")

        raw = campaign_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in campaign file: {exc}") from exc

        # Version check + migration
        source_version = data.get("version", 1)
        if source_version < CURRENT_SCHEMA_VERSION:
            data = migrate(data, CURRENT_SCHEMA_VERSION)

        # Validate via TypeAdapter
        try:
            self.campaign = campaign_adapter.validate_python(data)
        except Exception as exc:
            raise ValueError(f"Campaign schema validation failed: {exc}") from exc

        # Init progress and FSM
        cid = campaign_id or self.campaign.title
        self.slot_name = slot_name or "default"
        existing = self.load_progress(cid)
        if existing:
            self.progress = existing
            self._sync_fsm_from_progress()
        else:
            self.progress = CampaignProgress(
                campaign_id=cid,
                arc_index=start_arc_index,
                session_index=start_session_index,
                turn_in_session=0,
            )
            self._init_fsm()

        return self.campaign

    def is_loaded(self) -> bool:
        """Return True if a campaign is currently loaded."""
        return self.campaign is not None

    def get_opening_scene(self) -> str | None:
        """Return opening_scene for current session if campaign is loaded."""
        if self.campaign is None:
            return None
        if self.progress is None:
            if self.campaign.arcs and self.campaign.arcs[0].sessions:
                return self.campaign.arcs[0].sessions[0].opening_scene or None
            return None
        try:
            arc = self.campaign.arcs[self.progress.arc_index]
            session = arc.sessions[self.progress.session_index]
            return session.opening_scene or None
        except (IndexError, AttributeError):
            return None

    def load_progress(self, campaign_id: str) -> CampaignProgress | None:
        """Load progress from database. Returns None if no progress exists."""
        row = self.persistence.load(campaign_id, self.slot_name)
        if row is None:
            return None
        return CampaignProgress(
            campaign_id=row["campaign_id"],
            arc_index=row["arc_index"],
            session_index=row["session_index"],
            turn_in_session=row.get("turn_in_session", 0),
            revealed_anchors=json.loads(row.get("revealed_anchors", "[]")),
            completed_arcs=json.loads(row.get("completed_arcs", "[]")),
        )

    # ── Private ──────────────────────────────────────────────────────

    def _init_fsm(self) -> None:
        """Initialize FSM to start of campaign."""
        from app.services.campaign_fsm import CampaignStateMachine
        self.fsm = CampaignStateMachine()
        self.fsm.start_campaign()
        self.persistence.save(
            campaign_id=self.progress.campaign_id,
            slot_name=self.slot_name,
            arc_index=self.progress.arc_index,
            session_index=self.progress.session_index,
            turn_in_session=0,
            fsm_state=str(self.fsm.state),
            revealed_anchors=[],
            completed_arcs=[],
        )

    def _sync_fsm_from_progress(self) -> None:
        """Restore FSM state from persisted progress data."""
        if self.progress is None:
            return
        from app.services.campaign_fsm import CampaignStateMachine
        self.fsm = CampaignStateMachine()
        self.fsm.start_campaign()
        row = self.persistence.load(self.progress.campaign_id, self.slot_name)
        if row and row.get("fsm_state"):
            saved_state = row["fsm_state"]
            try:
                self.fsm.machine.set_state(saved_state)
            except Exception:
                logger.warning("FSM state restore failed for %r — using default", saved_state)
