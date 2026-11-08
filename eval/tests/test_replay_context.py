"""Integration tests for actual Jity context assembly; no network or model."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from jity_eval.replay.context import build_context, async_build_context, ContextBoundaryViolation, _NoCalls
from jity_eval.replay.sandbox import replay_sandbox


JITY_ROOT = Path(__file__).resolve().parents[2]


def fixture_dataset(count=12):
    initial = {"current_location": "STRUCT_LOCATION", "sanity": 71, "health": 83, "turn": 0,
               "player_status": {"condition": "STRUCT_CONDITION", "current_goal": "INITIAL_GOAL"},
               "items": [{"name": "struct_item", "status": "owned", "description": "STRUCT_ONLY_SENTINEL"}],
               "npcs": [{"name": "keeper", "description": "NPC_STRUCT_ONLY_SENTINEL"}],
               "quests": [], "world_facts": []}
    dataset = {"initial": {"turn_id": 100, "state": deepcopy(initial), "campaign_progress": {}}, "turns": []}
    for turn in range(1, count + 1):
        state = deepcopy(initial)
        state["turn"] = turn
        if turn >= 3:
            state["player_status"]["current_goal"] = "CHANGED_GOAL"
        state["recent_events"] = ["EVENT_ONLY_SENTINEL"]
        state["_memory_controller"] = {
            "version": "snapshot-%s" % turn, "round_unit": "turn", "pending": False,
            "nsb": {"level1": [{"episode_id": "ep_L1_1", "turn_start": 1, "turn_end": 4,
                                  "summary": "NARRATIVE_ONLY_SENTINEL", "tags": ["档案"], "importance": 0.8}]
                     if turn >= 4 else []},
            "pcb": {"sketches": {"player": {"entries": {
                "background": [{"value": "PERSONA_ONLY_SENTINEL", "turn": 2}]}}}} if turn >= 2 else {},
            "score_tracker": [{"item_name": "consumed_token", "state": "consumed", "last_seen_turn": 1}],
            "narrative_pool": [],
        }
        dataset["turns"].append({"turn": turn, "turn_id": 100 + turn, "player_action": "检查照明 %s" % turn,
                                 "output": {"narration": "LATE_HISTORY_%s" % turn, "dialogue": []},
                                 "state": state, "campaign_progress": {"recap_compressed": "RECAP_ONLY_SENTINEL"},
                                 "model_output": {"prompt_text": "OLD_DIRECTOR_ONLY_SENTINEL"}, "source": "llm"})
    return dataset


class ReplayContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.version_info < (3, 11):
            raise unittest.SkipTest("真实 Jity 集成测试需要 Python 3.11+；离线工具其他测试仍可用 Python 3.9")
        if not (JITY_ROOT / "backend/app").is_dir():
            raise unittest.SkipTest("旁边没有 Jity checkout")
        for dependency in ("numpy", "pydantic_settings", "tiktoken", "openai", "json_repair"):
            if importlib.util.find_spec(dependency) is None:
                raise unittest.SkipTest("缺少 Jity 依赖：" + dependency)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="jity-eval-context-")
        self.addCleanup(self.temporary.cleanup)
        self.guard = replay_sandbox(JITY_ROOT, Path(self.temporary.name))
        self.guard.__enter__()
        self.addCleanup(self.guard.__exit__, None, None, None)
        self.dataset = fixture_dataset()

    def test_three_modes_enforce_channels_without_mutating_backend(self):
        original = deepcopy(self.dataset)
        contexts = {mode: build_context(self.dataset, 12, "档案在哪里？", mode) for mode in ("A", "B", "C")}
        prompts = {mode: context["messages"][0]["content"] for mode, context in contexts.items()}
        for marker in ("NARRATIVE_ONLY_SENTINEL", "PERSONA_ONLY_SENTINEL", "RECAP_ONLY_SENTINEL", "EVENT_ONLY_SENTINEL"):
            self.assertIn(marker, prompts["A"])
            self.assertNotIn(marker, prompts["B"])
            self.assertNotIn(marker, prompts["C"])
        for marker in ("STRUCT_ONLY_SENTINEL", "NPC_STRUCT_ONLY_SENTINEL", "consumed_token"):
            self.assertIn(marker, prompts["A"])
            self.assertNotIn(marker, prompts["B"])
            self.assertIn(marker, prompts["C"])
        for mode, context in contexts.items():
            self.assertIn("LATE_HISTORY_12", prompts[mode])
            self.assertNotIn("OLD_DIRECTOR_ONLY_SENTINEL", prompts[mode])
            self.assertIsNone(context["probe_answer"])
            self.assertEqual(context["real_model_calls"], 0)
            self.assertTrue(context["leak_audit"]["passed"])
            self.assertEqual(context["backend_state_hash_before"], context["backend_state_hash_after"])
        self.assertEqual(len({c["checkpoint_input_hash"] for c in contexts.values()}), 1)
        self.assertEqual(self.dataset, original)
        self.assertNotIn("- 血条：", prompts["B"])
        self.assertNotIn("Context Memory / 长期记忆", prompts["B"])

    def test_real_retrieval_includes_provenance_and_no_embedding_api(self):
        with patch("tiktoken.get_encoding", side_effect=AssertionError("must not load/download vocabulary")):
            context = build_context(self.dataset, 12, "档案在哪里？", "full")
        hits = context["retrieval_hits"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["memory_id"], "ep_L1_1")
        self.assertEqual((hits[0]["turn_start"], hits[0]["turn_end"]), (1, 4))
        self.assertTrue(hits[0]["in_final_prompt"])
        self.assertIsNone(context["retrieval"]["embedding_client"])
        self.assertEqual(hits[0]["semantic_score"], 0)
        self.assertIn("MemoryController.assemble_context_async", context["pipeline_scope"]["reused"])

    def test_actual_truncation_sections_match_final_message(self):
        context = build_context(self.dataset, 12, "档案在哪里？", "full", budget=1)
        self.assertEqual("\n\n".join(context["sections_after"].values()), context["messages"][0]["content"])
        self.assertTrue(context["truncation"]["applied"])
        self.assertTrue(context["truncation"]["steps"])
        self.assertTrue(context["truncation"]["budget_exceeded"])
        self.assertNotIn("campaign_context", context["sections_after"])
        self.assertNotIn("messages", context["sections_after"])
        self.assertFalse(context["retrieval_hits"][0]["in_final_prompt"])
        self.assertEqual(context["injected_memory_hits"], [])

    def test_builder_hidden_message_and_structured_list_limits_are_recorded(self):
        self.dataset["turns"][-1]["output"]["narration"] = "甲" * 500 + "TAIL_MUST_BE_CLIPPED"
        self.dataset["turns"][-1]["state"]["items"] = [{"name": "item_%s" % i, "status": "owned"} for i in range(11)]
        context = build_context(self.dataset, 12, "继续", "state", recent_window=7)
        clips = context["truncation"]["message_clips"]
        self.assertEqual(len(clips), 14)
        self.assertEqual(sum(row["dropped_by_message_limit"] for row in clips), 4)
        self.assertTrue(clips[-1]["char_clipped"])
        self.assertEqual(clips[-1]["chars_after_builder"], 303)
        self.assertNotIn("TAIL_MUST_BE_CLIPPED", context["messages"][0]["content"])
        self.assertEqual(context["truncation"]["structured_list_counts"]["items"], {"input": 11, "rendered_limit": 8})
        self.assertEqual(context["provenance"]["recent_messages"][0]["source_turn"], 8)

    def test_initial_sources_remain_unknown_and_changes_are_not_last_mentions(self):
        context = build_context(self.dataset, 12, "继续", "state")
        provenance = {item["path"]: item for item in context["provenance"]["structured_state"]}
        self.assertIsNone(provenance["items[struct_item].description"]["source_turn"])
        changed = provenance["player_status.current_goal"]
        self.assertEqual(changed["source_turn"], 3)
        self.assertEqual(changed["basis"], "last_changed_snapshot")
        self.assertFalse(changed["is_last_mention"])

    def test_allowed_structured_overlap_is_not_mislabeled_as_narrative_leak(self):
        self.dataset["turns"][-1]["state"]["world_facts"] = [
            {"name": "clue", "description": "NARRATIVE_ONLY_SENTINEL", "status": "known"}]
        context = build_context(self.dataset, 12, "继续", "state")
        self.assertIn("NARRATIVE_ONLY_SENTINEL", context["messages"][0]["content"])
        self.assertTrue(context["leak_audit"]["passed"])
        self.assertTrue(any(item["channel"] == "narrative_memory" for item in context["leak_audit"]["allowed_input_overlaps"]))
        self.assertEqual(context["retrieval_hits"], [])

    def test_audit_detects_narrative_leak_if_channel_clear_regresses(self):
        from app.services.memory.nsb import NarrativeSummarizationBranch
        original_load = NarrativeSummarizationBranch.load_state

        def broken_clear(instance, data):
            if data:
                original_load(instance, data)

        with patch.object(NarrativeSummarizationBranch, "load_state", broken_clear):
            context = build_context(self.dataset, 12, "继续", "state")
        self.assertFalse(context["leak_audit"]["passed"])
        self.assertTrue(any(item["channel"] == "narrative_memory" for item in context["leak_audit"]["findings"]))

    def test_future_source_metadata_is_flagged_and_pending_maintenance_disclosed(self):
        memory = self.dataset["turns"][-1]["state"]["_memory_controller"]
        memory["pending"] = True
        memory["nsb"]["level1"][0]["turn_end"] = 50
        context = build_context(self.dataset, 12, "继续", "full")
        self.assertFalse(context["leak_audit"]["passed"])
        self.assertEqual(context["leak_audit"]["future_source_metadata"][0]["source_game_turn_end"], 50)
        self.assertTrue(context["pipeline_scope"]["snapshot_memory_pending"])

    def test_snapshot_and_recent_history_do_not_read_future_turns(self):
        self.dataset["turns"].append({"turn": 13, "turn_id": 113, "player_action": "FUTURE_SECRET",
                                      "output": {"narration": "FUTURE_SECRET"},
                                      "state": {"turn": 13, "current_location": "FUTURE_SECRET"}, "campaign_progress": {}})
        context = build_context(self.dataset, 12, "继续", "full")
        self.assertNotIn("FUTURE_SECRET", json.dumps(context, ensure_ascii=False))

    def test_zero_checkpoint_is_valid_and_bounds_are_checked(self):
        context = build_context(self.dataset, 0, "开始", "recent")
        self.assertEqual(context["provenance"]["recent_messages"], [])
        self.assertEqual(context["state_injection"]["model_visible_state"], {})
        for args in ((13, "recent", 5, 100), (True, "recent", 5, 100),
                     (0, "unknown", 5, 100), (0, "recent", 0, 100), (0, "recent", 5, 0)):
            with self.assertRaises(ValueError):
                build_context(self.dataset, args[0], "继续", args[1], args[2], args[3])

    def test_async_entrypoint_is_available_and_sync_rejects_running_loop(self):
        async def run():
            with self.assertRaisesRegex(RuntimeError, "async_build_context"):
                build_context(self.dataset, 12, "继续", "recent")
            return await async_build_context(self.dataset, 12, "继续", "recent")
        result = asyncio.run(run())
        self.assertEqual(result["mode"], "recent")

    def test_unexpected_database_or_llm_access_is_fatal_not_swallowed(self):
        with self.assertRaises(ContextBoundaryViolation):
            _NoCalls().generate_json
        with self.assertRaises(ContextBoundaryViolation):
            _NoCalls().add_knowledge_chunk


if __name__ == "__main__":
    unittest.main()
