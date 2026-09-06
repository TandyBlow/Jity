"""Wiring tests — the memory subsystem reaches the prompt and gets real inputs."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas import StoryOutput
from app.schemas.agent_io import EpisodeSummary, MemoryRecord
from app.schemas.game.memory import ItemMemory, MemoryUpdates
from app.services.memory.memory_controller import MemoryController
from app.services.memory.nsb import NarrativeSummarizationBranch
from app.services.scenario_generator.generator import ScenarioGenerator
from app.services.scenario_generator.prompting import PromptBuildMixin


def _make_controller() -> MemoryController:
    return MemoryController(llm_client=MagicMock(), db=MagicMock(), session_id="sess-1")


class _PromptGen(PromptBuildMixin):
    """Minimal host for PromptBuildMixin with ScenarioGenerator's static helpers."""

    _build_query = staticmethod(lambda player_action, state: player_action)
    _serialize_retrieved_chunks = staticmethod(lambda chunks: [])


class TestAssembleContext:
    def test_player_action_drives_l1_retrieval(self):
        mc = _make_controller()
        mc.nsb.get_retrieval_context = MagicMock(return_value=[
            SimpleNamespace(level=1, turn_start=0, turn_end=5, summary="第一章摘要"),
        ])
        state = {"npcs": [{"name": "诺诺"}], "recent_events": ["事件A", "事件B", "事件C"]}

        result = mc.assemble_context(
            state, turn=6, campaign_context="战役上下文", player_action="打开档案柜",
        )

        query = mc.nsb.get_retrieval_context.call_args[0][0]
        assert "打开档案柜" in query
        assert "诺诺" in query
        assert "战役上下文" in result
        assert "## 长期叙事记忆" in result
        assert "第一章摘要" in result

    def test_empty_memory_yields_campaign_context_only(self):
        mc = _make_controller()
        result = mc.assemble_context({}, turn=0, campaign_context="战役上下文", player_action="观察四周")
        assert result == "战役上下文"


class TestOnTurnGenerated:
    def test_pydantic_memory_updates_feed_score(self):
        mc = _make_controller()
        mc.on_turn_generated(
            "捡起通行卡", "你拿到了通行卡。", turn=3,
            memory_updates=MemoryUpdates(items_upserted=[ItemMemory(name="通行卡", status="owned")]),
        )
        assert "通行卡" in mc.score_tracker.get_all_states()

    def test_dict_memory_updates_feed_score(self):
        mc = _make_controller()
        mc.on_turn_generated(
            "a", "b", turn=1,
            memory_updates={"items_upserted": [{"name": "旧钥匙", "status": "owned"}]},
        )
        assert "旧钥匙" in mc.score_tracker.get_all_states()

    def test_none_memory_updates_is_safe(self):
        mc = _make_controller()
        mc.on_turn_generated("a", "b", turn=1, memory_updates=None)
        assert mc.score_tracker.get_all_states() == {}


class TestPromptWiring:
    def _make_gen(self, memory_ctrl) -> _PromptGen:
        gen = _PromptGen()
        gen.retriever = MagicMock()
        gen.retriever.retrieve_async = AsyncMock(return_value=[])
        gen.prompt_builder = MagicMock()
        gen.prompt_builder.build_sections.return_value = (
            {"system": "PROMPT"}, SimpleNamespace(temperature=0.7),
        )
        gen.db = MagicMock()
        gen.db.get_recent_messages.return_value = []
        gen._get_memory_controller = MagicMock(return_value=memory_ctrl)
        return gen

    @pytest.mark.asyncio
    async def test_memory_context_rides_campaign_channel(self):
        memory_ctrl = MagicMock()
        memory_ctrl.assemble_context.return_value = "战役+记忆上下文"
        gen = self._make_gen(memory_ctrl)

        cm = MagicMock()
        cm.is_loaded.return_value = True
        cm.progress.turn_in_session = 4
        cm.inject_context.return_value = "战役上下文"
        cm.truncate_prompt_sections.return_value = ("FINAL PROMPT", 12, None)

        request = SimpleNamespace(player_action="打开档案柜", style="horror", constraints="")
        prompt, meta, retrieved, rfs, token_count = await gen._build_prompt(
            request, {"turn": 4}, "sess-1", cm,
        )

        kwargs = memory_ctrl.assemble_context.call_args.kwargs
        assert kwargs["campaign_context"] == "战役上下文"
        assert kwargs["player_action"] == "打开档案柜"
        prompt_input = gen.prompt_builder.build_sections.call_args[0][0]
        assert prompt_input.campaign_context == "战役+记忆上下文"
        assert prompt == "FINAL PROMPT"
        assert token_count == 12

    @pytest.mark.asyncio
    async def test_no_campaign_skips_memory(self):
        memory_ctrl = MagicMock()
        gen = self._make_gen(memory_ctrl)
        request = SimpleNamespace(player_action="观察四周", style="horror", constraints="")

        prompt, meta, retrieved, rfs, token_count = await gen._build_prompt(
            request, {"turn": 0}, "sess-1", None,
        )

        gen._get_memory_controller.assert_not_called()
        prompt_input = gen.prompt_builder.build_sections.call_args[0][0]
        assert prompt_input.campaign_context == ""
        assert prompt == "PROMPT"
        assert token_count == 0


class TestNarratorStageMemory:
    def _make_generator(self) -> ScenarioGenerator:
        return ScenarioGenerator(
            db=None, state_manager=None, retriever=None, prompt_builder=None,
            llm_client=MagicMock(), scripted_story=None, default_model="deepseek-v4-flash",
        )

    @pytest.mark.asyncio
    async def test_narrator_stage_feeds_memory_and_schedules_maintain(self):
        gen = self._make_generator()
        output = StoryOutput(narration="你推开了档案室的门。")
        gen.llm_client.generate = AsyncMock(return_value=(output, 123))
        memory_ctrl = MagicMock()
        memory_ctrl.maintain = AsyncMock()
        gen._get_memory_controller = MagicMock(return_value=memory_ctrl)

        request = SimpleNamespace(player_action="捡起通行卡")
        meta = SimpleNamespace(temperature=0.7)
        out, latency_ms, source = await gen._run_narrator_stage(
            "sess-1", request, "PROMPT", "deepseek-v4-flash", meta, [], None, {"turn": 5}, 5,
        )

        assert source == "llm"
        assert latency_ms == 123
        memory_ctrl.on_turn_generated.assert_called_once_with(
            "捡起通行卡", "你推开了档案室的门。", 5, memory_updates=output.memory_updates,
        )
        await asyncio.gather(*gen._memory_tasks)
        memory_ctrl.maintain.assert_awaited_once()
        assert gen._memory_tasks == set()

    @pytest.mark.asyncio
    async def test_maintenance_task_failure_is_contained(self):
        gen = self._make_generator()

        async def boom() -> None:
            raise RuntimeError("maintain exploded")

        task = asyncio.create_task(boom())
        with pytest.raises(RuntimeError):
            await task
        gen._memory_tasks.add(task)
        gen._log_memory_task_done(task)  # must not raise
        assert task not in gen._memory_tasks


class TestMoomPool:
    def _make_controller(self) -> MemoryController:
        return MemoryController(llm_client=MagicMock(), db=MagicMock(), session_id="sess-1")

    @pytest.mark.asyncio
    async def test_accepted_l1_enters_moom_pool(self):
        mc = self._make_controller()
        mc.nsb.should_summarize_level1 = MagicMock(return_value=True)
        mc.nsb.summarize_level1 = AsyncMock(return_value=EpisodeSummary(
            episode_id="ep_L1_1", turn_start=4, turn_end=10, summary="巷战摘要", level=1,
        ))
        mc.nsb.should_summarize_level2 = MagicMock(return_value=False)
        mc.nsb.should_extract = MagicMock(return_value=False)
        mc._persist_episode = MagicMock()

        await mc.maintain("sess-1", turn=10)

        assert len(mc._narrative_pool) == 1
        rec = mc._narrative_pool[0]
        assert rec.memory_id == "ep_L1_1"
        assert rec.content == "巷战摘要"
        assert rec.created_round == 5  # forget_step rounds ≈ turn // 2
        mc._persist_episode.assert_called_once()

    @pytest.mark.asyncio
    async def test_pruned_episodes_sync_back_to_nsb(self):
        mc = self._make_controller()
        mc.nsb.accept_level1(EpisodeSummary(
            episode_id="ep_L1_old", turn_start=0, turn_end=5, summary="陈旧摘要", level=1,
        ))
        mc._narrative_pool.append(MemoryRecord(
            memory_id="ep_L1_old", content="陈旧摘要", created_round=0,
        ))
        mc.nsb.should_summarize_level1 = MagicMock(return_value=False)
        mc.nsb.should_extract = MagicMock(return_value=False)

        await mc.maintain("sess-1", turn=8)  # round 4: unreinforced score < threshold

        assert mc._narrative_pool == []
        assert mc.nsb._level1 == []  # pruned pool record removed from retrieval context

    @pytest.mark.asyncio
    async def test_promoted_l2_survives_l1_pruning(self):
        mc = self._make_controller()
        mc.nsb.accept_level1(EpisodeSummary(
            episode_id="ep_L1_old", turn_start=0, turn_end=5, summary="陈旧摘要", level=1,
        ))
        mc.nsb.accept_level2(EpisodeSummary(
            episode_id="ep_L2_1", turn_start=0, turn_end=5, summary="晋升的二级摘要", level=2,
        ))
        mc._narrative_pool.append(MemoryRecord(
            memory_id="ep_L1_old", content="陈旧摘要", created_round=0,
        ))
        mc.nsb.should_summarize_level1 = MagicMock(return_value=False)
        mc.nsb.should_extract = MagicMock(return_value=False)

        await mc.maintain("sess-1", turn=8)

        assert mc._narrative_pool == []
        assert mc.nsb._level1 == []
        assert [s.episode_id for s in mc.nsb._level2] == ["ep_L2_1"]  # gist survives

    @pytest.mark.asyncio
    async def test_failed_summary_leaves_pool_clean(self):
        mc = self._make_controller()
        mc.nsb.should_summarize_level1 = MagicMock(return_value=True)
        mc.nsb.summarize_level1 = AsyncMock(return_value=None)
        mc.nsb.should_summarize_level2 = MagicMock(return_value=False)
        mc.nsb.should_extract = MagicMock(return_value=False)
        mc._persist_episode = MagicMock()

        await mc.maintain("sess-1", turn=6)

        assert mc._narrative_pool == []
        mc._persist_episode.assert_not_called()

    def test_remove_episode_drops_from_l1(self):
        nsb = NarrativeSummarizationBranch(llm_client=MagicMock())
        nsb.accept_level1(EpisodeSummary(episode_id="ep_a", turn_start=0, turn_end=5, summary="A"))
        nsb.accept_level1(EpisodeSummary(episode_id="ep_b", turn_start=6, turn_end=10, summary="B"))

        nsb.remove_episode("ep_a")

        assert [s.episode_id for s in nsb._level1] == ["ep_b"]
