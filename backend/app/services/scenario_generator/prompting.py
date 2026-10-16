"""Hook 2 — prompt assembly (RAG retrieve → context injection → truncation)."""

import inspect

from app.services.scenario_generator.check_guidance import ending_player_action

from app.services.prompt_builder import PromptInput
from app.services.prompt_builder.prompts import (
    FINAL_TURNS_OPTION_CONTRACT,
    HARD_TURNS_OPTION_CONTRACT,
    SOFT_TURNS_OPTION_CONTRACT,
)
from app.services.campaign_endings import (
    ending_instruction, is_final_session, select_bloodline_collapse_ending,
    select_budget_ending, select_ending,
)


class PromptBuildMixin:
    @staticmethod
    def _select_campaign_ending(campaign_manager, state, player_action):
        """Use the same ending decision for opening, prompt and final output."""
        if campaign_manager is None or not campaign_manager.is_loaded():
            return None
        campaign = campaign_manager.campaign
        progress = campaign_manager.progress
        collapse = select_bloodline_collapse_ending(state)
        if collapse is not None:
            return collapse
        cap = campaign_manager.resolve_max_turns_per_campaign()
        if type(cap) is int:
            ending = select_budget_ending(campaign, progress, state, cap, player_action)
            if ending is not None:
                return ending
        return select_ending(campaign, progress, state, player_action)

    async def _build_prompt(self, request, state, session_id, campaign_manager):
        """RAG retrieve → context injection → truncation → return prompt + metadata."""
        query = self._build_query(request.player_action, state)
        retrieved = await self.retriever.retrieve_async(query)
        retrieved_for_storage = self._serialize_retrieved_chunks(retrieved)

        campaign_context = ""
        if campaign_manager is not None and campaign_manager.is_loaded():
            turn = getattr(campaign_manager.progress, "turn_in_session", int(state.get("turn", 0)))
            campaign_context = campaign_manager.inject_context(state, turn)
            progress = campaign_manager.progress
            closing_pending = campaign_manager.is_closing_pending()
            should_close = campaign_manager.should_begin_closing_after_next_turn()
            hard_limit = campaign_manager.is_hard_limit_reached()
            forced_anchor = None
            if type(hard_limit) is bool and hard_limit:
                forced_anchor = campaign_manager.stage_forced_completion_anchor()
            if type(closing_pending) is bool and closing_pending and not is_final_session(
                campaign_manager.campaign, progress
            ):
                next_name = self._next_campaign_session_name(campaign_manager)
                next_opening = self._next_campaign_opening(campaign_manager)
                campaign_context += (
                    "\n## 转场行动执行指令\n"
                    "上一回合已经完成本幕收束，玩家当前提交的是正式转场选择。"
                    "必须完整执行这个选择，写清行动后果、移动过程、人物反应和代价；不得拒绝、改写或跳过。\n"
                    f"目标下一幕：{next_name}。目标场景事实：{next_opening}\n"
                    "本回合结尾应自然抵达该场景的行动入口。输出选项必须是在新场景中立刻可执行的不同推进方式。"
                )
            elif forced_anchor is not None:
                campaign_context += (
                    "\n## 核心剧情强制补完指令\n"
                    f"{HARD_TURNS_OPTION_CONTRACT}"
                    "本回合必须完成的核心事件：\n"
                    f"- {forced_anchor.name}：{forced_anchor.description}"
                )
            elif type(should_close) is bool and should_close and not is_final_session(
                campaign_manager.campaign, progress
            ):
                next_name = self._next_campaign_session_name(campaign_manager)
                campaign_context += (
                    "\n## 本幕收束指令\n"
                    "这是本幕最后一个常规回合。先完整兑现玩家当前行动及其后果，"
                    "再用一个明确事件把当前矛盾连接到下一幕。不要突然传送、跳时或宣告任务完成。\n"
                    f"下一幕：{next_name}。结尾选项必须是进入下一幕的不同方式，"
                    "每项都要带来不同的线索、风险、关系或资源变化；不要提供继续观察、等待等空转选项。"
                )
            elif type(hard_limit) is bool and hard_limit and is_final_session(
                campaign_manager.campaign, progress
            ):
                choices = self._final_choice_focus(campaign_manager, state)
                campaign_context += (
                    "\n## 最终幕强制抉择指令\n"
                    "最终幕核心真相已经补齐。先完整兑现玩家当前行动，让危机升级到必须立即选择的状态；"
                    "本回合不能因为局部上限而结束战役。\n"
                    f"{FINAL_TURNS_OPTION_CONTRACT}"
                    f"当前可用的确定性结局触发短语：\n{choices}"
                )
            else:
                soft_limit = campaign_manager.is_soft_limit_reached()
                if type(soft_limit) is bool and soft_limit:
                    focus = self._soft_turns_focus(campaign_manager)
                    campaign_context += (
                        "\n## 本幕推进指令\n"
                        "本幕已到达软回合阈值，进入主线收束期。当前行动之后必须出现能接近本幕核心事件的明确变化。\n"
                        f"{SOFT_TURNS_OPTION_CONTRACT}"
                        f"本幕未完成的收束目标：\n{focus}"
                    )
            selected_ending = self._select_campaign_ending(
                campaign_manager, state, ending_player_action(request)
            )
            if selected_ending is not None:
                campaign_context += "\n" + ending_instruction(selected_ending)

            # Keep memory in the campaign context channel so token truncation
            # accounts for it.  The controller's async variant is used when
            # available; the synchronous API remains compatible with tests
            # and lightweight callers.
            memory_ctrl = self._get_memory_controller(session_id, state, campaign_manager)
            async_assemble = getattr(memory_ctrl, "assemble_context_async", None)
            if inspect.iscoroutinefunction(async_assemble):
                campaign_context = await async_assemble(
                    state,
                    int(state.get("turn", 0)),
                    campaign_context=campaign_context,
                    player_action=request.player_action,
                )
            else:
                campaign_context = memory_ctrl.assemble_context(
                    state,
                    int(state.get("turn", 0)),
                    campaign_context=campaign_context,
                    player_action=request.player_action,
                )

        current_campaign_session = None
        if campaign_manager is not None and campaign_manager.is_loaded():
            current_campaign_session = getattr(campaign_manager.progress, "session_index", 0)

        prompt_input = PromptInput(
            player_action=request.player_action,
            game_state=state,
            retrieved_chunks=retrieved,
            style=request.style,
            constraints=request.constraints,
            campaign_context=campaign_context,
            # Previous sessions are represented by the campaign recap.  Mixing
            # their raw turns into "最近对话" after a scripted opening can pull
            # Narrator back into the scene that just ended.
            recent_messages=self.db.get_recent_messages(
                session_id,
                campaign_session_index=current_campaign_session,
            ),
        )
        prompt_sections, meta = self.prompt_builder.build_sections(prompt_input)
        prompt = "\n\n".join(prompt_sections.values())
        token_count = 0

        if campaign_manager is not None and campaign_manager.is_loaded():
            prompt, token_count, _ = campaign_manager.truncate_prompt_sections(prompt_sections)
            from app.services.memory.memory_controller import MemoryController
            if isinstance(memory_ctrl, MemoryController):
                retrieved_for_storage.extend(memory_ctrl.record_injected(prompt, int(state.get("turn", 0))))

        return prompt, meta, retrieved, retrieved_for_storage, token_count

    @staticmethod
    def _next_campaign_session_name(campaign_manager) -> str:
        """Return the next authored session label without mutating progress."""
        campaign = campaign_manager.campaign
        progress = campaign_manager.progress
        try:
            arc = campaign.arcs[progress.arc_index]
            if progress.session_index + 1 < len(arc.sessions):
                return f"{arc.name} — {arc.sessions[progress.session_index + 1].name}"
            next_arc = campaign.arcs[progress.arc_index + 1]
            return f"{next_arc.name} — {next_arc.sessions[0].name}"
        except (AttributeError, IndexError, TypeError):
            return "后续章节"

    @staticmethod
    def _next_campaign_opening(campaign_manager) -> str:
        campaign = campaign_manager.campaign
        progress = campaign_manager.progress
        try:
            arc = campaign.arcs[progress.arc_index]
            if progress.session_index + 1 < len(arc.sessions):
                return arc.sessions[progress.session_index + 1].opening_scene
            return campaign.arcs[progress.arc_index + 1].sessions[0].opening_scene
        except (AttributeError, IndexError, TypeError):
            return "承接当前事件进入后续章节。"

    @staticmethod
    def _soft_turns_focus(campaign_manager) -> str:
        """Describe concrete unrevealed goals that every soft-limit option must advance."""
        try:
            campaign = campaign_manager.campaign
            progress = campaign_manager.progress
            arc = campaign.arcs[progress.arc_index]
            session = arc.sessions[progress.session_index]
            revealed = set(progress.revealed_anchors or [])
            completion_ids = set(session.completion_anchors or [])
            anchors = [
                anchor for anchor in session.anchor_events
                if anchor.id not in revealed
                and (not completion_ids or anchor.id in completion_ids)
            ]
            if not anchors:
                anchors = [
                    anchor for anchor in session.anchor_events
                    if anchor.id not in revealed
                ]
            if anchors:
                return "\n".join(
                    f"- {anchor.name}：{anchor.description}" for anchor in anchors
                )
            return f"- 推进并解决当前章节目标：{arc.goal or session.name}"
        except (AttributeError, IndexError, TypeError):
            return "- 推进当前主线目标，形成不可逆的新信息、决定或局势变化"

    @staticmethod
    def _final_choice_focus(campaign_manager, state: dict) -> str:
        """List structurally eligible deterministic ending phrases for Narrator."""
        try:
            campaign = campaign_manager.campaign
            progress = campaign_manager.progress
            revealed = set(progress.revealed_anchors or [])
            owned = {
                item.get("name", "") for item in state.get("items", [])
                if isinstance(item, dict)
                and item.get("status", "owned") in {"owned", "active", "carried", "持有", "拥有"}
            }
            routes = []
            for route in campaign.ending_routes or []:
                if route.category == "bad":
                    continue
                if not set(route.required_items or []).issubset(owned):
                    continue
                if not set(route.required_anchors or []).issubset(revealed):
                    continue
                phrases = [phrase for phrase in (route.trigger_phrases or []) if phrase.strip()]
                if phrases:
                    routes.append(f"- {route.name}：" + " / ".join(phrases))
            if routes:
                return "\n".join(routes)
        except (AttributeError, TypeError):
            pass
        return "- 根据已经揭示的真相给出 3 到 4 个明确、不可逆的最终选择"
