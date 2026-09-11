"""CampaignSessionAdvancer — turn/session/arc advancement orchestration."""

import logging
from typing import Any

from app.services.campaign_persistence import CampaignPersistence
from app.services.campaign_recap import CampaignRecapGenerator

logger = logging.getLogger(__name__)


class CampaignSessionAdvancer:
    """Orchestrates campaign-local turn increments and session/arc boundaries."""

    DEFAULT_MAX_TURNS = 30

    def __init__(
        self,
        persistence: CampaignPersistence,
        recap_generator: CampaignRecapGenerator,
    ) -> None:
        self.persistence = persistence
        self.recap = recap_generator

    def advance_turn(
        self,
        progress: Any,
        fsm: Any,
        slot_name: str,
    ) -> int:
        """Increment turn_in_session and persist. Returns new turn count."""
        if progress is None:
            return 0
        progress.turn_in_session += 1
        self.persistence.save(
            campaign_id=progress.campaign_id,
            slot_name=slot_name,
            arc_index=progress.arc_index,
            session_index=progress.session_index,
            turn_in_session=progress.turn_in_session,
            fsm_state=str(fsm.state) if fsm.state else "idle",
            revealed_anchors=progress.revealed_anchors,
            completed_arcs=progress.completed_arcs,
        )
        return progress.turn_in_session

    def resolve_max_turns(self, campaign: Any, progress: Any) -> int:
        """Resolve max_turns_per_session with precedence chain."""
        # 1. Per-session override in campaign.json
        if campaign and progress:
            try:
                arc = campaign.arcs[progress.arc_index]
                session = arc.sessions[progress.session_index]
                session_max = getattr(session, "max_turns_per_session", None)
                if session_max is not None:
                    return session_max
            except (IndexError, AttributeError):
                pass

        # 2. Campaign-level default
        if campaign:
            campaign_max = getattr(campaign, "max_turns_per_session", None)
            if campaign_max is not None:
                return campaign_max

        # 3. option_config.json global default
        import json
        from pathlib import Path

        try:
            config_path = Path(__file__).resolve().parents[2] / "scripts" / "option_config.json"
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                return config.get("max_turns_per_session", self.DEFAULT_MAX_TURNS)
        except Exception:
            logger.debug("option_config.json load failed", exc_info=True)

        # 4. Hardcoded default — MUST return int, never None
        return self.DEFAULT_MAX_TURNS

    async def advance_session(
        self,
        campaign: Any,
        progress: Any,
        fsm: Any,
        slot_name: str,
    ) -> str:
        """Advance to next campaign session. Returns recap text."""
        if progress is None or campaign is None:
            return ""

        recap = ""
        try:
            recap = await self.recap.generate_recap(progress.campaign_id)
        except Exception:
            logger.warning("Recap generation failed in advance_session, using structural fallback", exc_info=True)
            recap = self.recap.build_structural_recap(campaign, progress)
        if recap:
            self.recap.store_recap(
                self.persistence,
                progress.campaign_id, slot_name, progress,
                str(fsm.state) if fsm.state else "idle",
                recap,
            )

        self.persistence.decay_npc_relations(progress.campaign_id, slot_name)

        # Check if this is the last session in the arc
        try:
            arc = campaign.arcs[progress.arc_index]
            is_last_session = progress.session_index + 1 >= len(arc.sessions)
        except IndexError:
            is_last_session = True

        if is_last_session:
            return await self.advance_arc(campaign, progress, fsm, slot_name)

        # Normal session advance
        fsm.end_session()
        fsm.resume_session()
        progress.session_index += 1
        progress.turn_in_session = 0
        self.persistence.save(
            campaign_id=progress.campaign_id,
            slot_name=slot_name,
            arc_index=progress.arc_index,
            session_index=progress.session_index,
            turn_in_session=0,
            fsm_state=str(fsm.state) if fsm.state else "idle",
            revealed_anchors=progress.revealed_anchors,
            completed_arcs=progress.completed_arcs,
        )
        return recap

    async def advance_arc(
        self,
        campaign: Any,
        progress: Any,
        fsm: Any,
        slot_name: str,
    ) -> str:
        """Advance to next arc. Returns recap text."""
        if progress is None or campaign is None:
            return ""

        recap = ""
        try:
            recap = await self.recap.generate_recap(progress.campaign_id)
        except Exception:
            logger.warning("Recap generation failed in advance_arc, using structural fallback", exc_info=True)
            recap = self.recap.build_structural_recap(campaign, progress)
        if recap:
            self.recap.store_recap(
                self.persistence,
                progress.campaign_id, slot_name, progress,
                str(fsm.state) if fsm.state else "idle",
                recap,
            )

        # Arc boundary
        fsm.end_session()
        fsm.arc_transition()
        fsm.begin_arc()
        fsm.session_active()
        progress.arc_index += 1
        progress.session_index = 0
        progress.turn_in_session = 0
        progress.completed_arcs.append(progress.arc_index - 1)
        self.persistence.save(
            campaign_id=progress.campaign_id,
            slot_name=slot_name,
            arc_index=progress.arc_index,
            session_index=0,
            turn_in_session=0,
            fsm_state=str(fsm.state) if fsm.state else "idle",
            revealed_anchors=progress.revealed_anchors,
            completed_arcs=progress.completed_arcs,
        )
        return recap
