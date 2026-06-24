"""CampaignManager — campaign lifecycle: load, FSM, anchors, context injection.

Single coordinating service owning all campaign-aware concerns.
Each concern in a focused method.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from app.database import Database
from app.schemas.campaign import (
    AnchorEvent,
    AnchorTriggerConditions,
    CampaignSchema,
    CampaignProgress,
    migrate,
    campaign_adapter,
    CURRENT_SCHEMA_VERSION,
)
from app.schemas.game import StoryOutput

from app.services.campaign_fsm import CampaignStateMachine
from app.services.context_strategy import (
    ContextStrategy,
    SimpleTruncationStrategy,
    get_token_encoder,
)
from app.services.prompt_builder import build_fact_extraction

class CampaignManager:
    """Owns campaign lifecycle: load campaign.json, init FSM, manage progress,
    evaluate anchors, inject context.

    Each concern in a focused method. Constructor receives dependencies via
    manual DI (same pattern as ScenarioGenerator).
    """

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
        self.campaign: CampaignSchema | None = None
        self.progress: CampaignProgress | None = None
        self.slot_name = "default"
        self.fsm = CampaignStateMachine()
        self._anchor_cooldowns: dict[str, int] = {}
        self._pending_anchor_triggers: list[tuple[str, int]] = []
        self._strategy: ContextStrategy = SimpleTruncationStrategy()  # anchor_type -> last_triggered_turn

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
        3. Run migration chain (v1→v2→v3)
        4. Validate against CampaignSchema via TypeAdapter
        5. Cache in self.campaign
        6. Init FSM and progress (from start_arc_index/start_session_index)
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

        # Validate via TypeAdapter (independent validation)
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

    def _init_fsm(self) -> None:
        """Initialize FSM to start of campaign.

        Recreates the FSM to reset to idle state before starting.
        This is needed because CampaignManager is a singleton and
        may have leftover FSM state from a previous session.
        """
        from app.services.campaign_fsm import CampaignStateMachine
        self.fsm = CampaignStateMachine()
        self.fsm.start_campaign()
        self._persist_progress()

    def _sync_fsm_from_progress(self) -> None:
        """Restore FSM state from persisted progress data."""
        if self.progress is None:
            return
        # Recreate FSM to reset to a clean state before applying saved state
        from app.services.campaign_fsm import CampaignStateMachine
        self.fsm = CampaignStateMachine()
        self.fsm.start_campaign()
        row = self.db.read_campaign_progress(self.progress.campaign_id, self.slot_name)
        if row and row.get("fsm_state"):
            saved_state = row["fsm_state"]
            try:
                self.fsm.machine.set_state(saved_state)
            except Exception:
                logger.warning("FSM state restore failed for %r — using default", saved_state)

    def save_progress(self) -> None:
        """Persist current progress and FSM state to database."""
        if self.progress is None:
            return
        self._persist_progress()

    def _persist_progress(self) -> None:
        """Write progress to DB immediately (Pitfall 5: no deferred saves)."""
        if self.progress is None:
            return
        recap_compressed, recap_full = self._current_recap_fields()
        self.db.write_campaign_progress(
            campaign_id=self.progress.campaign_id,
            arc_index=self.progress.arc_index,
            session_index=self.progress.session_index,
            turn_in_session=getattr(self.progress, "turn_in_session", 0),
            fsm_state=str(self.fsm.state) if self.fsm.state else "idle",
            revealed_anchors=self.progress.revealed_anchors,
            completed_arcs=self.progress.completed_arcs,
            recap_compressed=recap_compressed,
            recap_full=recap_full,
            slot_name=self.slot_name,
        )

    def load_progress(self, campaign_id: str) -> CampaignProgress | None:
        """Load progress from database. Returns None if no progress exists."""
        row = self.db.read_campaign_progress(campaign_id, self.slot_name)
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

    def get_opening_scene(self) -> str | None:
        """Return opening_scene for current session if campaign is loaded.

        Returns None if no campaign is loaded OR if the current session
        has no opening_scene set. The caller (ScenarioGenerator) uses
        None as the signal to fall through to ScriptedStory.
        """
        if self.campaign is None:
            return None
        if self.progress is None:
            # If campaign loaded but no progress yet, use first session
            if (
                self.campaign.arcs
                and self.campaign.arcs[0].sessions
            ):
                return self.campaign.arcs[0].sessions[0].opening_scene or None
            return None
        # Use progress to find current session
        try:
            arc = self.campaign.arcs[self.progress.arc_index]
            session = arc.sessions[self.progress.session_index]
            return session.opening_scene or None
        except (IndexError, AttributeError):
            return None

    def is_loaded(self) -> bool:
        """Return True if a campaign is currently loaded."""
        return self.campaign is not None

    # ── Session recap (CAMP-08) ──

    async def generate_recap(self, session_id: str) -> str | None:
        """Generate LLM-compressed recap from session_messages history.

        Uses deepseek-v4-flash (cheap) for non-real-time boundary call.
        Returns the compressed recap string, or None on failure.
        """
        if self.llm_client is None or self.prompt_builder is None:
            return None

        messages = self.db.get_messages(session_id)
        if not messages:
            return None

        try:
            recap_prompt = self.prompt_builder.build_recap(messages)
            recap_text = await self.llm_client.generate_text(
                recap_prompt, model="deepseek-v4-flash", max_tokens=800
            )
            return recap_text.strip()
        except Exception:
            logger.warning("Recap generation failed for campaign %s", self.progress.campaign_id, exc_info=True)
            return None

    def store_recap(self, recap_text: str) -> None:
        """Store both compressed and full recap in campaign_progress.

        Full recap appends to existing full recap (cumulative history).
        Compressed recap is the latest single-session summary.
        """
        if self.progress is None:
            return
        row = self.db.read_campaign_progress(self.progress.campaign_id, self.slot_name)
        existing_full = row.get("recap_full", "") if row else ""
        self._persist_progress_with_recap(
            compressed=recap_text,
            full=(existing_full + "\n\n" + recap_text).strip() if existing_full else recap_text,
        )

    def _is_first_turn_of_session(self, turn_in_session: int) -> bool:
        """Return True if this is the first turn of a new campaign session.

        Uses turn_in_session (campaign session counter, resets at boundaries)
        instead of state["turn"] (game session total, never resets).
        """
        if self.fsm is None:
            return turn_in_session == 0
        return turn_in_session == 0

    def _load_recap_compressed(self) -> str:
        """Load the compressed recap from campaign_progress."""
        if self.progress is None:
            return ""
        row = self.db.read_campaign_progress(self.progress.campaign_id, self.slot_name)
        if row:
            return row.get("recap_compressed", "")
        return ""

    def _current_recap_fields(self) -> tuple[str, str]:
        """Preserve existing recap fields when writing unrelated progress."""
        if self.progress is None:
            return "", ""
        row = self.db.read_campaign_progress(self.progress.campaign_id, self.slot_name)
        if not isinstance(row, dict):
            return "", ""
        return row.get("recap_compressed", ""), row.get("recap_full", "")

    def _persist_progress_with_recap(self, compressed: str, full: str) -> None:
        """Write progress with recap fields to DB."""
        if self.progress is None:
            return
        self.db.write_campaign_progress(
            campaign_id=self.progress.campaign_id,
            arc_index=self.progress.arc_index,
            session_index=self.progress.session_index,
            turn_in_session=getattr(self.progress, "turn_in_session", 0),
            fsm_state=str(self.fsm.state) if self.fsm.state else "idle",
            revealed_anchors=self.progress.revealed_anchors,
            completed_arcs=self.progress.completed_arcs,
            recap_compressed=compressed,
            recap_full=full,
            slot_name=self.slot_name,
        )

    # ── Health monitoring integration (CAMP-09) ──

    def inject_health(self) -> str | None:
        """Return health guidance context string, or None if no guidance needed.

        Called by inject_context() every turn. Guidance is throttled internally
        by HealthMonitor cooldowns.
        """
        # HealthMonitor is set externally after construction
        monitor = getattr(self, "_health_monitor", None)
        if monitor is None or self.progress is None:
            return None

        turn = getattr(self.progress, "turn_in_session", 0)
        try:
            metrics = monitor.compute(self.progress.campaign_id, turn)
        except Exception:
            logger.warning("Health metric computation failed for campaign %s", self.progress.campaign_id, exc_info=True)
            return None

        if not metrics.needs_guidance:
            return None

        return self._build_health_guidance(metrics)

    def _build_health_guidance(self, health: Any) -> str:
        """Build diegetic narrative guidance from health metrics.

        Maps each HealthGuidanceHint to a narrative instruction.
        Never uses direct "your story is broken" language.
        """
        hints_map = {
            "pacing_slow": "叙事节奏提示：当前剧情进展较慢，可适当引入新的环境变化或NPC行动来推动局面。",
            "pacing_fast": "叙事节奏提示：当前事件推进较快，可适当放慢节奏，让玩家有时间消化线索和角色互动。",
            "dialogue_heavy": "叙事平衡提示：对话占比较高，可适当增加环境描写和行动后果，保持叙事与互动的平衡。",
            "tension_plateau": "叙事张力提示：当前局势趋于平稳，可在背景中埋设新的悬念或暗示即将到来的变化。",
            "clue_starvation": "叙事线索提示：最近揭示的线索较少，可通过环境细节、NPC对话或意外发现提供新的调查方向。",
        }

        parts = ["## 叙事健康引导"]
        for hint in health.guidance_hints:
            hint_name = hint.value if hasattr(hint, "value") else str(hint)
            if hint_name in hints_map:
                parts.append(hints_map[hint_name])
        return "\n".join(parts) if len(parts) > 1 else None

    # ── Fact extraction (CAMP-07a) ──

    async def extract_facts(self, narration_text: str, recent_events: list[str]) -> list[dict]:
        """LLM-driven fact extraction from recent narrative content.

        Uses deepseek-v4-flash (cheap) every 5 turns. Not in blocking path
        — caller should fire-and-forget.

        Returns list of world fact dicts ready for merge into game state.
        """
        if self.llm_client is None or self.prompt_builder is None:
            return []

        prompt = build_fact_extraction(narration_text, recent_events)
        try:
            facts = await self.llm_client.generate_json(
                prompt, model="deepseek-v4-flash", max_tokens=2000, temperature=0.2
            )
            if isinstance(facts, list):
                return [f for f in facts if isinstance(f, dict) and f.get("name")]
            return []
        except Exception:
            logger.warning("Fact extraction failed for campaign %s", self.progress.campaign_id, exc_info=True)
            return []

    # ── Deviation detection (CAMP-07) ──

    def detect_deviation(self, state: dict[str, Any], turn: int) -> bool:
        """Detect if player has deviated from expected anchor path.

        Returns True if the player has been in the same location for 3+
        consecutive turns without triggering any anchor, suggesting
        they are exploring off the planned path.
        """
        # Check if any anchors were triggered recently
        if self.progress is None or self.campaign is None:
            return False

        # Sustained deviation: 3+ turns without anchor trigger in current session
        try:
            arc = self.campaign.arcs[self.progress.arc_index]
            session = arc.sessions[self.progress.session_index]
            total_session_anchors = len(session.anchor_events)
            revealed_in_session = [
                a_id for a_id in self.progress.revealed_anchors
                if any(a.id == a_id for a in session.anchor_events)
            ]
            # If >3 turns into session and no anchors revealed yet, likely deviating
            if turn >= 3 and total_session_anchors > 0 and len(revealed_in_session) == 0:
                return True
        except IndexError:
            pass

        return False

    def generate_adaptive_anchors(self, state: dict[str, Any]) -> list[AnchorEvent]:
        """Generate adaptive anchors when player deviates from planned path.

        Creates temporary anchors based on current game state context.
        Capped at 3 dynamic anchors per session.
        """
        if self.progress is None or self.campaign is None:
            return []

        # Check dynamic anchor cap
        dynamic_count = sum(
            1 for a_id in self.progress.revealed_anchors
            if a_id.startswith("dynamic-")
        )
        if dynamic_count >= 3:
            return []

        # Generate anchors based on current state
        location = state.get("current_location", "")
        npc_names = [n.get("name", "") for n in state.get("npcs", [])]

        new_anchors = []
        idx = dynamic_count + 1

        # Location-based anchor
        if location:
            new_anchors.append(AnchorEvent(
                id=f"dynamic-{self.progress.arc_index}-{self.progress.session_index}-{idx}",
                name=f"探索：{location}",
                description=f"玩家在当前地点 '{location}' 的探索中发现了新的线索",
                priority=3,
                trigger_conditions=AnchorTriggerConditions(location=location),
            ))

        return new_anchors[:3]  # cap at 3

    # ── Anchor event evaluation (CAMP-02) ──

    def evaluate_anchors(self, state: dict[str, Any], turn: int) -> list[AnchorEvent]:
        """Evaluate all pending anchors for the current session against game state.

        Hard-filter by location/NPC/item, check cooldown, sort by priority.
        Returns at most 1 anchor (highest priority = lowest priority number) per turn.

        Args:
            state: Current game state dict
            turn: Current turn number

        Returns:
            List of 0 or 1 AnchorEvent that should trigger this turn
        """
        if self.campaign is None or self.progress is None:
            return []

        # Get current session's anchor events
        try:
            arc = self.campaign.arcs[self.progress.arc_index]
            session = arc.sessions[self.progress.session_index]
            anchors = list(session.anchor_events)
        except IndexError:
            return []

        if self.detect_deviation(state, turn) or (turn >= 3 and not anchors):
            anchors.extend(self.generate_adaptive_anchors(state))

        # Filter: not already revealed
        candidates = [
            a for a in anchors
            if a.id not in self.progress.revealed_anchors
        ]

        # Filter: hard conditions met
        candidates = [
            a for a in candidates
            if self._conditions_met(a.trigger_conditions, state)
        ]

        # Filter: cooldown (>=3 turns since same anchor type)
        candidates = [
            a for a in candidates
            if self._check_cooldown(a.id, turn)
        ]

        if not candidates:
            return []

        # Sort by priority (lower number = higher priority)
        candidates.sort(key=lambda a: a.priority)

        # Return at most 1 anchor per turn
        return candidates[:1]

    def _conditions_met(
        self, conditions: AnchorTriggerConditions, state: dict[str, Any]
    ) -> bool:
        """Check if all non-None hard-filter conditions match current state.

        All specified conditions must match (AND logic).
        A None condition means "don't check" — it always passes.
        """
        # Location match
        if conditions.location is not None:
            current_location = state.get("current_location", "")
            if conditions.location not in current_location:
                return False

        # NPC present match
        if conditions.npc_present is not None:
            npc_names = [npc.get("name", "") for npc in state.get("npcs", [])]
            if conditions.npc_present not in npc_names:
                return False

        # Item held match
        if conditions.item_held is not None:
            item_names = [item.get("name", "") for item in state.get("items", [])]
            if conditions.item_held not in item_names:
                return False

        return True

    def _check_cooldown(self, anchor_id: str, turn: int) -> bool:
        """Return True if the anchor is off cooldown (>=3 turns since last trigger)."""
        last_triggered = self._anchor_cooldowns.get(anchor_id, -999)
        return (turn - last_triggered) >= 3

    def mark_anchor_triggered(self, anchor_id: str, turn: int) -> None:
        """Record that an anchor was triggered this turn."""
        if self.progress is not None:
            if anchor_id not in self.progress.revealed_anchors:
                self.progress.revealed_anchors.append(anchor_id)
        self._anchor_cooldowns[anchor_id] = turn
        self._persist_progress()

    def commit_pending_anchors(self) -> list[str]:
        """Mark anchors that were injected into a successful turn prompt."""
        if not self._pending_anchor_triggers:
            return []
        triggered: list[str] = []
        for anchor_id, turn in self._pending_anchor_triggers:
            self.mark_anchor_triggered(anchor_id, turn)
            triggered.append(anchor_id)
        self._pending_anchor_triggers = []
        return triggered

    def advance_turn(self) -> int:
        """Increment the campaign-local turn counter and persist it."""
        if self.progress is None:
            return 0
        self.progress.turn_in_session += 1
        self._persist_progress()
        return self.progress.turn_in_session

    def _describe_trigger(self, anchor: AnchorEvent) -> str:
        """Build a diegetic redirection instruction for the anchor.

        Returns a prompt instruction that guides the LLM to naturally steer
        toward the anchor — no hard 'you cannot do that' denials.
        """
        return (
            f"叙事引导：玩家即将触发锚点事件「{anchor.name}」。\n"
            f"锚点描述：{anchor.description}\n"
            "请通过环境线索、NPC暗示、或剧情推动自然地引导玩家接近该事件。\n"
            "不要直接告诉玩家发生了什么，让玩家自己的选择引领他们到达那里。\n"
            "如果玩家的当前行动与该锚点方向完全不同，等待更好的时机——今天的线索终将浮现。"
        )

    # ── Context injection (CAMP-03) ──

    def inject_context(self, state: dict[str, Any], turn: int) -> str:
        """Build campaign context string for injection into PromptInput.campaign_context.

        Includes: arc/session position, anchor progress, candidate triggers,
        next anchor hint. Called every turn when a campaign is loaded.

        Args:
            state: Current game state dict
            turn: Current turn number

        Returns:
            Context string (Chinese) ready for prompt injection, or empty string
        """
        if self.campaign is None or self.progress is None:
            return ""

        parts = []

        # Arc/session position
        arc_idx = self.progress.arc_index
        session_idx = self.progress.session_index
        try:
            current_arc = self.campaign.arcs[arc_idx]
            current_session = current_arc.sessions[session_idx]
            parts.append(f"当前章节：{current_arc.name} — {current_session.name}")
            parts.append(f"章节目标：{current_arc.goal or '无'}")
        except IndexError:
            parts.append("当前章节：无")

        # Anchor progress
        total_anchors = sum(
            len(s.anchor_events)
            for a in self.campaign.arcs
            for s in a.sessions
        )
        dynamic_revealed = sum(1 for a_id in self.progress.revealed_anchors if a_id.startswith("dynamic-"))
        total_anchors += dynamic_revealed
        revealed_count = len(self.progress.revealed_anchors)
        parts.append(f"锚点进度：{revealed_count}/{total_anchors} 已揭示")

        # Recap layer (03-01): inject "Previously on..." at session start
        turn_in_session = getattr(self.progress, "turn_in_session", 0) if self.progress else 0
        if self._is_first_turn_of_session(turn_in_session):
            recap = self._load_recap_compressed()
            if recap:
                parts.insert(0, "## 前情提要\n" + recap)

        # NPC relations block (top-3 by absolute affinity)
        if self.progress:
            row = self.db.read_campaign_progress(self.progress.campaign_id, self.slot_name)
            if row:
                try:
                    relations = json.loads(row.get("npc_relations", "[]"))
                    if relations:
                        sorted_rels = sorted(relations, key=lambda r: abs(r.get("affinity", 0)), reverse=True)
                        top3 = sorted_rels[:3]
                        rel_lines = ["## 人物关系变化"]
                        for r in top3:
                            name = r.get("name", "未知")
                            affinity = r.get("affinity", 0)
                            if affinity > 0:
                                change_desc = "信任上升"
                            elif affinity < 0:
                                change_desc = "敌意加深"
                            else:
                                change_desc = "中性"
                            rel_lines.append(f"- {name}: {change_desc} (当前好感: {affinity:+d})")
                        parts.append("\n".join(rel_lines))
                except (json.JSONDecodeError, KeyError):
                    pass

        # Candidate triggers this turn
        turn_in_session = getattr(self.progress, "turn_in_session", turn) if self.progress else turn
        self._pending_anchor_triggers = []
        candidates = self.evaluate_anchors(state, turn_in_session)
        if candidates:
            anchor = candidates[0]
            self._pending_anchor_triggers = [(anchor.id, turn_in_session)]
            parts.append(self._describe_trigger(anchor))

        # Health guidance layer (03-04)
        health_context = self.inject_health()
        if health_context:
            parts.append(health_context)

        return "\n".join(parts)

    # ── Token budget (CAMP-03a) ──

    TOKEN_BUDGET_LIMIT = 102400  # 80% of assumed 128K context window
    _enc = None

    def check_token_budget(self, prompt: str) -> tuple[bool, int, str]:
        """Check if prompt exceeds token budget.

        Delegates to ContextStrategy for counting and threshold.
        Uses cl100k_base encoding (conservative for Chinese).

        Returns:
            Tuple of (ok: bool, token_count: int, message: str)
        """
        token_count = self._strategy.count_tokens(prompt)
        if self._strategy.should_truncate(token_count):
            return (
                False,
                token_count,
                f"警告：token计数 {token_count} 超过预算 {self._strategy.budget_limit}",
            )
        return True, token_count, ""

    def truncate_prompt_sections(self, sections: dict[str, str]) -> tuple[str, int, bool]:
        """Return a prompt built from sections, truncating low-priority blocks if needed."""
        prompt = "\n\n".join(sections.values())
        token_count = self._strategy.count_tokens(prompt)
        if not self._strategy.should_truncate(token_count):
            return prompt, token_count, False
        truncated = self._strategy.truncate(sections)
        return truncated, self._strategy.count_tokens(truncated), True

    # ── Per-turn instrumentation (CAMP-09a) ──

    def record_turn(
        self,
        output: StoryOutput,
        state: dict[str, Any],
        latency_ms: int,
    ) -> dict[str, int]:
        """Record lightweight per-turn instrumentation metrics.

        Returns a dict of metric values to store alongside the model output.
        """
        narration = output.narration
        dialogue = output.dialogue or []
        options = output.options or []

        location_before = state.get("current_location", "")
        location_after = output.current_location or location_before

        return {
            "word_count": len(narration),
            "option_count": len(options),
            "sanity_delta": output.sanity_delta,
            "health_delta": output.health_delta,
            "dialogue_lines": len(dialogue),
            "location_changed": 1 if location_after != location_before else 0,
            "token_count": 0,  # filled by caller after prompt build
        }

    # ── Session auto-advance (CAMP-PACE) ──

    DEFAULT_MAX_TURNS = 30

    def resolve_max_turns(self) -> int:
        """Resolve max_turns_per_session with precedence:
        per-session override > campaign-level > option_config.json > DEFAULT (30).
        """
        # 1. Per-session override in campaign.json
        if self.campaign and self.progress:
            try:
                arc = self.campaign.arcs[self.progress.arc_index]
                session = arc.sessions[self.progress.session_index]
                session_max = getattr(session, "max_turns_per_session", None)
                if session_max is not None:
                    return session_max
            except (IndexError, AttributeError):
                pass

        # 2. Campaign-level default (future v4 schema field)
        if self.campaign:
            campaign_max = getattr(self.campaign, "max_turns_per_session", None)
            if campaign_max is not None:
                return campaign_max

        # 3. option_config.json global default
        try:
            config_path = Path(__file__).resolve().parents[2] / "scripts" / "option_config.json"
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                return config.get("max_turns_per_session", self.DEFAULT_MAX_TURNS)
        except Exception:
            logger.debug("option_config.json load failed", exc_info=True)

    def _build_structural_recap(self) -> str:
        """Build a structural recap from campaign data when LLM recap fails."""
        if self.progress is None or self.campaign is None:
            return ""

        parts = ["## 前情提要（结构摘要）", ""]
        try:
            arc = self.campaign.arcs[self.progress.arc_index]
            parts.append(f"完成了 {self.progress.arc_index} 个叙事弧")
            parts.append(f"当前弧：{arc.name}")
            parts.append(f"弧目标：{arc.goal or '无'}")
        except IndexError:
            parts.append("战役完成")

        if self.progress.revealed_anchors:
            parts.append(f"已揭示锚点：{len(self.progress.revealed_anchors)} 个")

        parts.append("（LLM 前情提要生成失败，此处为结构摘要。）")
        return "\n".join(parts)

    def _decay_npc_relations(self) -> None:
        """Decay all NPC affinities toward 0 by 1 at session boundary."""
        if self.progress is None:
            return
        row = self.db.read_campaign_progress(self.progress.campaign_id, self.slot_name)
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
                self.progress.campaign_id,
                json.dumps(relations, ensure_ascii=False),
                self.slot_name,
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("NPC relations decode failed for campaign %s", self.progress.campaign_id)

    async def advance_session(self) -> str:
        """Advance to next campaign session. Returns recap text."""
        if self.progress is None or self.campaign is None:
            return ""

        recap = ""
        try:
            recap = await self.generate_recap(self.progress.campaign_id)
        except Exception:
            logger.warning("Recap generation failed in advance_session, using structural fallback", exc_info=True)
            recap = self._build_structural_recap()
        if recap:
            self.store_recap(recap)

        self._decay_npc_relations()

        # Check if this is the last session in the arc
        try:
            arc = self.campaign.arcs[self.progress.arc_index]
            is_last_session = self.progress.session_index + 1 >= len(arc.sessions)
        except IndexError:
            is_last_session = True

        if is_last_session:
            return await self.advance_arc()

        # Normal session advance: end_session → recap → resume → persist
        self.fsm.end_session()
        self.fsm.resume_session()
        self.progress.session_index += 1
        self.progress.turn_in_session = 0
        self._pending_anchor_triggers = []
        self._persist_progress()
        return recap

    async def advance_arc(self) -> str:
        """Advance to next arc. Returns recap text."""
        if self.progress is None or self.campaign is None:
            return ""

        recap = ""
        try:
            recap = await self.generate_recap(self.progress.campaign_id)
        except Exception:
            logger.warning("Recap generation failed in advance_session, using structural fallback", exc_info=True)
            recap = self._build_structural_recap()
        if recap:
            self.store_recap(recap)

        # Arc boundary: skip resume_session, go directly to arc transition
        self.fsm.end_session()
        self.fsm.arc_transition()
        self.fsm.begin_arc()
        self.fsm.session_active()
        self.progress.arc_index += 1
        self.progress.session_index = 0
        self.progress.turn_in_session = 0
        self._pending_anchor_triggers = []
        self.progress.completed_arcs.append(self.progress.arc_index - 1)
        self._persist_progress()
        return recap
