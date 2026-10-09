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

import json
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

    def end_campaign(self, *, persist: bool = True) -> None:
        """Move the active campaign to its terminal FSM state and persist it.

        ``persist=False`` defers the write to the turn's commit_story_turn
        transaction, same as the other advancement paths.
        """
        if self.progress is None:
            return
        self.fsm.end_campaign()
        if persist:
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

    def progress_snapshot(self) -> dict:
        """Full campaign_progress row dict for the current in-memory progress.

        The advancing fields (arc/session/turn/anchors/arcs-done/fsm) come
        from memory, which on the deferred path is ahead of the database
        until commit_story_turn writes them. Recap and npc_relations are
        memory-less: preserve whatever storage holds so the snapshot upsert
        cannot wipe them.
        """
        if self.progress is None:
            return {}
        row = self.db.read_campaign_progress(
            self.progress.campaign_id, self.slot_name
        ) or {}
        recap_compressed, recap_full = self._persistence._current_recap_fields(
            self.progress.campaign_id, self.slot_name
        )
        return {
            "campaign_id": self.progress.campaign_id,
            "slot_name": self.slot_name,
            "arc_index": self.progress.arc_index,
            "session_index": self.progress.session_index,
            "turn_in_session": self.progress.turn_in_session,
            "fsm_state": str(self.fsm.state) if self.fsm.state else "idle",
            "revealed_anchors": json.dumps(
                self.progress.revealed_anchors, ensure_ascii=False
            ),
            "completed_arcs": json.dumps(
                self.progress.completed_arcs, ensure_ascii=False
            ),
            "recap_compressed": recap_compressed,
            "recap_full": recap_full,
            "npc_relations": row.get("npc_relations", "[]") or "[]",
        }

    def reload_runtime_state(self) -> None:
        """Discard in-memory advancement and re-derive progress + FSM from storage.

        Called after a failed turn commit so a retried request cannot double-
        advance on stale in-memory counters.
        """
        if self.progress is None:
            return
        progress = self._loader.load_progress(self.progress.campaign_id)
        if progress is not None:
            self._loader.progress = progress
        self._loader._sync_fsm_from_progress()

    def flush_deferred_effects(self) -> None:
        """Apply side effects deferred by the turn's in-memory advancement.

        Currently only the session-boundary NPC relation decay. Called after
        the node commit succeeded; a failed commit drops the pending effect
        and the retried boundary re-defers it.
        """
        if self._advancer.relation_decay_pending:
            self._advancer.relation_decay_pending = False
            if self.progress is not None:
                self._persistence.decay_npc_relations(
                    self.progress.campaign_id, self.slot_name
                )

    def reset_to_initial(self) -> None:
        """Reset progress and FSM to the campaign's initial state.

        Used when a node without a progress snapshot (e.g. the pre-campaign
        root) is activated: the initial snapshot that node lacks is applied
        here instead of keeping whichever progress the previous branch had.
        """
        if self.progress is None:
            return
        self._loader._init_fsm()
        progress = self._loader.load_progress(self.progress.campaign_id)
        if progress is not None:
            self._loader.progress = progress
