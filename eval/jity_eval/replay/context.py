"""Build auditable A/B/C probe contexts with Jity's local implementation.

No Jity import occurs at module import time. The caller supplies the frozen
dataset, Jity's import path and its process-level network guard. This module
never calls a model, writes a database, or uses a historical answer as the
answer to a new probe.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
from typing import Any

from .sandbox import ForbiddenReplayOperation


MODES = {"A": "full", "B": "recent", "C": "state", "full": "full", "recent": "recent", "state": "state"}
STRUCTURED_KEYS = ("current_location", "sanity", "health", "turn", "player_status", "items", "npcs", "quests", "world_facts")
COMMON_HEADER = "你是桌面 RPG 的中文 GM 辅助系统，负责根据玩家行动生成合理、连贯、可交互的下一段剧情。\n"


class ContextBoundaryViolation(ForbiddenReplayOperation):
    """Do not let Jity's Exception fallbacks hide unexpected external work."""


class _NoCalls:
    def __getattr__(self, name):
        raise ContextBoundaryViolation("上下文组装不允许调用模型或数据库：" + name)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate(dataset, checkpoint_turn, question, mode, recent_window, budget):
    if mode not in MODES:
        raise ValueError("mode 必须是 A/B/C 或 full/recent/state")
    if type(checkpoint_turn) is not int or checkpoint_turn < 0:
        raise ValueError("checkpoint_turn 必须是非负整数")
    if type(recent_window) is not int or recent_window < 1:
        raise ValueError("recent_window 必须是正整数")
    if type(budget) is not int or budget < 1:
        raise ValueError("budget 必须是正整数")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question 必须是非空字符串")
    if not isinstance(dataset, dict) or not isinstance(dataset.get("initial"), dict):
        raise ValueError("dataset 缺少 initial 检查点")
    turns = dataset.get("turns")
    if not isinstance(turns, list) or checkpoint_turn > len(turns):
        raise ValueError("checkpoint_turn 超出冻结历史范围")
    for index, turn in enumerate(turns[:checkpoint_turn], 1):
        if not isinstance(turn, dict) or type(turn.get("turn")) is not int or turn["turn"] != index:
            raise ValueError("冻结时间线 turn 必须从 1 连续递增")
    checkpoint = dataset["initial"] if checkpoint_turn == 0 else turns[checkpoint_turn - 1]
    if not isinstance(checkpoint.get("state"), dict):
        raise ValueError("检查点缺少完整 state")
    return checkpoint, turns[:checkpoint_turn], MODES[mode]


def _flatten(value, path=""):
    """Paths use entity names where possible, so reordering is not a write."""
    result = {}
    if isinstance(value, dict):
        for key, item in value.items():
            result.update(_flatten(item, (path + "." if path else "") + str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            identity = item.get("name", index) if isinstance(item, dict) else index
            result.update(_flatten(item, "%s[%s]" % (path, identity)))
    else:
        result[path] = value
    return result


def _structured_provenance(dataset, history, visible_state):
    previous = _flatten(dataset["initial"]["state"])
    latest = {}
    for row in history:
        current = _flatten(row["state"])
        for path, value in current.items():
            if path not in previous or previous[path] != value:
                latest[path] = row
        previous = current
    records = []
    for path, value in _flatten(visible_state).items():
        row = latest.get(path)
        records.append({
            "path": path, "value": value,
            "source_turn": row["turn"] if row else None,
            "source_turn_id": row.get("turn_id") if row else None,
            "source_game_turn": row["state"].get("turn") if row else None,
            "basis": "last_changed_snapshot" if row else "unknown_initial_snapshot",
            "is_last_mention": False,
        })
    return records


def _recent_messages(history, recent_window):
    messages = []
    for row in history[-recent_window:]:
        output = row.get("output")
        if not isinstance(output, dict):
            raise ValueError("冻结回合缺少已记录的剧情 output")
        for role, content in (("user", row.get("player_action", "")),
                              ("assistant", json.dumps(output, ensure_ascii=False))):
            if not isinstance(content, str):
                raise ValueError("冻结玩家行动必须是字符串")
            messages.append({"role": role, "content": content, "source_turn": row["turn"],
                             "source_turn_id": row.get("turn_id"),
                             "source_game_turn": row["state"].get("turn")})
    return messages


def _narrative_values(memory):
    records = []
    for level in ("level1", "level2", "level3"):
        for summary in memory.get("nsb", {}).get(level, []):
            records.append(("narrative_memory", summary.get("summary", "")))
    pcb = memory.get("pcb", {})
    sketches = pcb.get("sketches", {})
    if not sketches and pcb.get("sketch"):
        sketches = {"player": pcb["sketch"]}
    for name, sketch in sketches.items():
        for key, values in sketch.get("entries", {}).items():
            for value in values:
                if isinstance(value, dict):
                    records.append(("persona", value.get("value", "")))
    return records


def _leak_audit(mode, state, memory, recap, final_prompt, allowed_inputs):
    forbidden = []
    if mode != "full":
        forbidden.extend(_narrative_values(memory))
        forbidden.append(("recap", recap))
        forbidden.extend(("recent_events", v) for v in state.get("recent_events", []))
    if mode == "recent":
        forbidden.extend(("structured_state", value) for value in _flatten(
            {key: state[key] for key in STRUCTURED_KEYS if key in state}
        ).values())
        for value in memory.get("score_tracker", []):
            forbidden.append(("score_tracker", value.get("item_name", "")))
    findings, overlaps = [], []
    seen = set()
    for channel, value in forbidden:
        # Exact-match auditing is deliberately distinct from semantic checking.
        if not isinstance(value, str) or len(value.strip()) < 2 or (channel, value) in seen:
            continue
        seen.add((channel, value))
        if value not in final_prompt:
            continue
        entry = {"channel": channel, "text": value}
        if value in allowed_inputs:
            overlaps.append(entry)
        else:
            findings.append(entry)
    return {"passed": not findings, "findings": findings, "allowed_input_overlaps": overlaps,
            "method": "channel_allowlist_and_exact_text_scan",
            "checked_unique_values": len(seen),
            "limitations": ["相同事实可合法出现在近期消息、问题或允许的结构化字段中。",
                            "精确文本扫描不等于语义泄漏检测；同义转述需人工复核。"]}


def build_context(dataset: dict, checkpoint_turn: int, question: str, mode: str,
                  recent_window: int = 5, budget: int = 102400) -> dict:
    """Synchronous entry point; async callers should await async_build_context."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_build_context(dataset, checkpoint_turn, question, mode, recent_window, budget))
    raise RuntimeError("运行中的事件循环请 await async_build_context(...)，不要调用同步 build_context")


async def async_build_context(dataset: dict, checkpoint_turn: int, question: str, mode: str,
                              recent_window: int = 5, budget: int = 102400) -> dict:
    checkpoint, history, mode = _validate(dataset, checkpoint_turn, question, mode, recent_window, budget)
    # These imports are intentionally inside the boundary supplied by the runner.
    from app.services.memory.memory_controller import MemoryController
    from app.services.prompt_builder import PromptBuilder, PromptInput
    from app.services.context_strategy import SimpleTruncationStrategy, _FallbackEncoding

    backend_before = _hash(checkpoint["state"])
    backend_state = deepcopy(checkpoint["state"])
    memory = deepcopy(backend_state.get("_memory_controller") or {})
    progress = deepcopy(checkpoint.get("campaign_progress") or {})
    recap = progress.get("recap_compressed") or ""
    if not isinstance(recap, str):
        raise ValueError("冻结 recap_compressed 必须是字符串")
    game_turn = backend_state.get("turn")
    if type(game_turn) is not int:
        raise ValueError("检查点 state.turn 必须是整数")
    checkpoint_hash = _hash({"turn": checkpoint_turn, "turn_id": checkpoint.get("turn_id"),
                             "state": backend_state, "campaign_progress": progress})
    controller = MemoryController(_NoCalls(), _NoCalls(), "offline-context", embedding_client=None)
    controller.load_state(memory)
    controller.score_tracker.seed(backend_state.get("items", []), game_turn)
    if mode != "full":
        # This is a branch-local model-view controller. The authoritative
        # backend snapshot and its persistent memory are never erased.
        controller.nsb.load_state({})
        controller.pcb.load_state({})
    if mode == "recent":
        controller.score_tracker.load_from_state([])
        controller.score_tracker._aliases = {}
    visible_state = {} if mode == "recent" else {
        key: deepcopy(backend_state[key]) for key in STRUCTURED_KEYS if key in backend_state
    }
    if mode == "full" and "recent_events" in backend_state:
        visible_state["recent_events"] = deepcopy(backend_state["recent_events"])
    campaign_context = "## 前情提要\n" + recap if mode == "full" and recap else ""
    campaign_context = await controller.assemble_context_async(
        visible_state, game_turn, campaign_context=campaign_context, player_action=question)
    retrieved = [hit.model_dump(mode="json") for hit in controller.last_hits]
    recent = _recent_messages(history, recent_window)

    class ProbePromptBuilder(PromptBuilder):
        def _system_header(self, input, player_status):
            if mode == "recent":
                return COMMON_HEADER
            return super()._system_header(input, player_status)

    prompt_input = PromptInput(player_action=question, game_state=visible_state,
                               retrieved_chunks=[], campaign_context=campaign_context,
                               recent_messages=recent)
    builder = ProbePromptBuilder()
    sections_before, meta = builder.build_sections(prompt_input)

    class TracedStrategy(SimpleTruncationStrategy):
        def __init__(self):
            super().__init__(budget_limit=budget)
            self._enc = _FallbackEncoding()  # Never download a tokenizer.
            self.final_sections = deepcopy(sections_before)
            self.steps = []

        def _build_truncated(self, sections, trun_index):
            rendered = super()._build_truncated(sections, trun_index)
            self.final_sections = deepcopy(rendered)
            self.steps.append({"levels": dict(trun_index),
                               "tokens": self.count_tokens("\n\n".join(rendered.values())),
                               "section_chars": {key: len(value) for key, value in rendered.items()}})
            return rendered

    strategy = TracedStrategy()
    prompt_before = "\n\n".join(sections_before.values())
    final_prompt = strategy.truncate(sections_before)
    sections_after = strategy.final_sections
    if "\n\n".join(sections_after.values()) != final_prompt:
        raise RuntimeError("裁剪审计与实际最终 prompt 不一致")
    injected = controller.record_injected(final_prompt, game_turn)
    retained_ids = {hit["id"] for hit in injected}
    for hit in retrieved:
        hit["in_final_prompt"] = hit["memory_id"] in retained_ids
    visible_recent = recent[-10:]
    message_clips = []
    for index, message in enumerate(recent):
        kept = index >= max(0, len(recent) - 10)
        content = message["content"]
        display = content if len(content) <= 300 else content[:300] + "..."
        message_clips.append({"role": message["role"], "source_turn": message["source_turn"],
                              "source_turn_id": message["source_turn_id"],
                              "chars_before": len(content), "chars_after_builder": len(display) if kept else 0,
                              "dropped_by_message_limit": not kept,
                              "char_clipped": kept and len(content) > 300,
                              "in_final_prompt": kept and display in sections_after.get("messages", "")})
    state_provenance = _structured_provenance(dataset, history, visible_state)
    for record in state_provenance:
        record["text_match_in_final_prompt"] = isinstance(record["value"], str) and bool(record["value"]) and record["value"] in final_prompt
    persona_provenance = []
    if mode == "full":
        for name, sketch in controller.pcb._sketches.items():
            for key, values in sketch.entries.items():
                for value in values:
                    mapped = [row["turn"] for row in history if row["state"].get("turn") == value.turn]
                    persona_provenance.append({"character": name, "key": key, "value": value.value,
                                               "source_game_turn": value.turn,
                                               "source_turn": mapped[0] if len(mapped) == 1 else None,
                                               "in_final_prompt": "%s(T%s)" % (value.value, value.turn) in final_prompt})
    score_records = [record.model_dump(mode="json") for record in controller.score_tracker.all_records()]
    score_provenance = []
    for record in score_records:
        mapped = [row["turn"] for row in history if row["state"].get("turn") == record["last_seen_turn"]]
        score_provenance.append({"item_name": record["item_name"], "state": record["state"],
                                 "source_game_turn": record["last_seen_turn"],
                                 "source_turn": mapped[0] if len(mapped) == 1 else None,
                                 "basis": "SCORE last_seen_turn; not necessarily last narrative mention"})
    excluded = ["historical_director_instructions", "campaign_opening_and_anchor_hints", "external_rag_knowledge"]
    if mode != "full":
        excluded += ["narrative_memory", "persona", "recap", "recent_events"]
    if mode == "recent":
        excluded += ["structured_state", "score_tracker"]
    policy = {"mode": mode, "recent_messages": True, "narrative_memory": mode == "full",
              "persona": mode == "full", "recap": mode == "full",
              "structured_state": mode != "recent", "score_tracker": mode != "recent",
              "recent_events": mode == "full", "excluded": excluded,
              "common_game_rules": "Jity PromptBuilder static role, style and output contracts",
              "backend_state_retained": True}
    # Remove all non-allowed channels when constructing an audit reference.
    allowed_sections, _ = builder.build_sections(PromptInput(
        player_action=question, game_state=visible_state, recent_messages=recent, retrieved_chunks=[]))
    if mode != "recent" and score_records:
        allowed_sections["score_tracker"] = "\n".join("- %s: %s" % (record["item_name"], record["state"]) for record in score_records)
    allowed_inputs = "\n\n".join(allowed_sections.values())
    audit = _leak_audit(mode, backend_state, memory, recap, final_prompt, allowed_inputs)
    future_sources = [{"channel": "narrative_memory", "memory_id": hit["memory_id"],
                       "source_game_turn_end": hit["turn_end"]} for hit in retrieved
                      if hit["in_final_prompt"] and hit["turn_end"] > game_turn]
    future_sources.extend({"channel": "persona", "character": value["character"],
                           "source_game_turn": value["source_game_turn"]} for value in persona_provenance
                          if value["in_final_prompt"] and value["source_game_turn"] > game_turn)
    audit["future_source_metadata"] = future_sources
    audit["passed"] = audit["passed"] and not future_sources
    after_hash = _hash(checkpoint["state"])
    if after_hash != backend_before:
        raise RuntimeError("上下文组装修改了冻结后端检查点")
    return {
        "schema_version": 1, "mode": mode, "checkpoint_turn": checkpoint_turn,
        "checkpoint_turn_id": checkpoint.get("turn_id"), "checkpoint_input_hash": checkpoint_hash,
        "backend_state_hash_before": backend_before, "backend_state_hash_after": after_hash,
        "messages": [{"role": "user", "content": final_prompt}],
        "sections_before": sections_before, "sections_after": sections_after,
        "retrieval_hits": retrieved, "injected_memory_hits": injected,
        "retrieval": {"implementation": "Jity MemoryController / NSB retrieve_hits",
                      "embedding_client": None, "ranking": "entity_tag_importance_recency",
                      "semantic_retrieval_reproduced": False,
                      "query": controller._build_retrieval_query(visible_state, question)},
        "state_injection": {"model_visible_state": visible_state, "score_tracker": score_records,
                            "full_backend_snapshot_in_messages": False,
                            "note": "C 中允许结构化条目的 description/notes 等字段；来源为结构化记录。"},
        "channel_policy": policy,
        "truncation": {"budget": budget, "encoder": "Jity._FallbackEncoding (offline estimate)",
                       "tokens_before": strategy.count_tokens(prompt_before),
                       "tokens_after": strategy.count_tokens(final_prompt),
                       "budget_exceeded": strategy.count_tokens(final_prompt) > budget,
                       "applied": final_prompt != prompt_before, "steps": strategy.steps,
                       "section_chars_before": {k: len(v) for k, v in sections_before.items()},
                       "section_chars_after": {k: len(v) for k, v in sections_after.items()},
                       "builder_limits": {"recent_messages": 10, "message_chars": 300,
                                          "structured_items_per_kind": 8, "rag_chunk_chars": 1200},
                       "message_clips": message_clips,
                       "structured_list_counts": {key: {"input": len(visible_state.get(key, [])),
                                                           "rendered_limit": min(8, len(visible_state.get(key, [])))}
                                                  for key in ("items", "npcs", "quests", "world_facts")}},
        "provenance": {"recent_messages": [{k: v for k, v in row.items() if k != "content"} for row in visible_recent],
                       "structured_state": state_provenance, "persona": persona_provenance,
                       "score_tracker": score_provenance,
                       "narrative_memory": [{"memory_id": hit["memory_id"], "source_game_turn_start": hit["turn_start"],
                                             "source_game_turn_end": hit["turn_end"], "in_final_prompt": hit["in_final_prompt"]}
                                            for hit in retrieved],
                       "recap": {"provided_to_builder": mode == "full" and bool(recap),
                                 "exact_full_text_in_final_prompt": mode == "full" and bool(recap) and recap in final_prompt,
                                 "source_turn": None,
                                 "basis": "unknown; frozen checkpoint recap has no source-turn field"},
                       "structured_source_note": "source_turn 为最后发生值变化的冻结快照，不能解释为最后提及回合。"},
        "leak_audit": audit, "real_model_calls": 0, "probe_answer": None,
        "pipeline_scope": {
            "reused": ["MemoryController.load_state", "MemoryController.assemble_context_async",
                       "MemoryController.record_injected", "PromptBuilder.build_sections", "SimpleTruncationStrategy.truncate"],
            "not_executed": ["ScenarioGenerator.generate", "Director", "Narrator", "memory maintenance", "external RAG retrieval"],
            "recent_history_scope": "last N frozen timeline turns; not production chapter filtering",
            "snapshot_memory_pending": bool(memory.get("pending", False)),
            "snapshot_scope": "frozen persisted checkpoint; pending maintenance is not executed by context assembly",
            "purpose": "actual offline probe context assembly; no probe answer or model capability score",
        },
    }
