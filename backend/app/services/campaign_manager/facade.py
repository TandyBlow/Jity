"""CampaignManager — thin facade delegating to focused campaign services.

Owns the lifecycle state (campaign, progress, slot_name, fsm) and delegates
each concern to a dedicated service:
  - CampaignLoader: loading, FSM init, validation
  - CampaignPersistence: DB read/write
  - CampaignAnchorEvaluator: anchor evaluation, commit, conditions, cooldown
  - CampaignRecapGenerator: LLM recap, storage, structural fallback
  - CampaignContextBuilder: prompt injection string assembly
  - CampaignSessionAdvancer: turn/session/arc advancement

All public method signatures are preserved so callers (ScenarioGenerator,
routes, tests) remain unchanged.
"""

import logging
from pathlib import Path

from app.database import Database
from app.schemas.campaign import (
    CampaignProgress,
    CampaignSchema,
)
from app.services.campaign_advancer import CampaignSessionAdvancer
from app.services.campaign_anchors import CampaignAnchorEvaluator
from app.services.campaign_context import CampaignContextBuilder
from app.services.campaign_fsm import CampaignStateMachine
from app.services.campaign_loader import CampaignLoader
from app.services.campaign_persistence import CampaignPersistence
from app.services.campaign_recap import CampaignRecapGenerator
from app.services.context_strategy import (
    ContextStrategy,
    SimpleTruncationStrategy,
)

from app.services.campaign_manager.facades import AnchorFacade
from app.services.campaign_manager.metrics import MetricsFacade
from app.services.campaign_manager.recap_advancer import RecapAdvancerFacade

logger = logging.getLogger(__name__)


class CampaignManager(AnchorFacade, RecapAdvancerFacade, MetricsFacade):
    """Thin facade — delegates each concern to a focused service."""

    def __init__(
        self,
        db: Database,
        campaigns_dir: Path,
        scripted_story,
        prompt_builder=None,
        llm_client=None,
        health_monitor=None,
    ) -> None:
        self.db = db
        self.campaigns_dir = campaigns_dir
        self.scripted_story = scripted_story
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self._health_monitor = health_monitor

        # ── Sub-services ──
        self._persistence = CampaignPersistence(db)
        self._loader = CampaignLoader(db, self._persistence)
        self._anchors = CampaignAnchorEvaluator()
        self._recap = CampaignRecapGenerator(db, llm_client, prompt_builder)
        self._advancer = CampaignSessionAdvancer(self._persistence, self._recap)
        self._context = CampaignContextBuilder(
            db, self._anchors, self._recap, health_monitor
        )
        self._strategy: ContextStrategy = SimpleTruncationStrategy()  # public for tests

    # ── Properties (preserve old API) ────────────────────────────────

    @property
    def campaign(self) -> CampaignSchema | None:
        return self._loader.campaign

    @campaign.setter
    def campaign(self, value: CampaignSchema | None) -> None:
        self._loader.campaign = value

    @property
    def progress(self) -> CampaignProgress | None:
        return self._loader.progress

    @progress.setter
    def progress(self, value: CampaignProgress | None) -> None:
        self._loader.progress = value

    @property
    def slot_name(self) -> str:
        return self._loader.slot_name

    @slot_name.setter
    def slot_name(self, value: str) -> None:
        self._loader.slot_name = value

    @property
    def fsm(self) -> CampaignStateMachine:
        return self._loader.fsm

    @fsm.setter
    def fsm(self, value: CampaignStateMachine) -> None:
        self._loader.fsm = value

    # ── Loading / Init ───────────────────────────────────────────────

    def load(
        self,
        campaign_path: Path,
        campaign_id: str | None = None,
        start_arc_index: int = 0,
        start_session_index: int = 0,
        slot_name: str = "default",
    ) -> CampaignSchema:
        return self._loader.load(
            campaign_path, campaign_id, start_arc_index, start_session_index, slot_name
        )

    def end_campaign(self) -> None:
        """Move the active campaign to its terminal FSM state and persist it."""
        if self.progress is None:
            return
        self.fsm.end_campaign()
        self._persistence.save(
            campaign_id=self.progress.campaign_id,
            slot_name=self.slot_name,
            arc_index=self.progress.arc_index,
            session_index=self.progress.session_index,
            turn_in_session=self.progress.turn_in_session,
            fsm_state=str(self.fsm.state),
            revealed_anchors=self.progress.revealed_anchors,
            completed_arcs=self.progress.completed_arcs,
        )

    def is_loaded(self) -> bool:
        return self._loader.is_loaded()

    def get_opening_scene(self) -> str | None:
        return self._loader.get_opening_scene()

    # ── Persistence ──────────────────────────────────────────────────

    def save_progress(self) -> None:
        if self.progress is None:
            return
        self._persistence.save(
            campaign_id=self.progress.campaign_id,
            slot_name=self.slot_name,
            arc_index=self.progress.arc_index,
            session_index=self.progress.session_index,
            turn_in_session=getattr(self.progress, "turn_in_session", 0),
            fsm_state=str(self.fsm.state) if self.fsm.state else "idle",
            revealed_anchors=self.progress.revealed_anchors,
            completed_arcs=self.progress.completed_arcs,
        )

    def _persist_progress(self) -> None:
        self.save_progress()

    def load_progress(self, campaign_id: str) -> CampaignProgress | None:
        return self._loader.load_progress(campaign_id)
