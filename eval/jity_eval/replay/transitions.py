"""Audit Jity's real state/memory boundary on independent recorded checkpoints.

This is deliberately not ScenarioGenerator.generate: campaign advancement,
Director generation and original embedding requests require additional tapes.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path

from ..storage import atomic_json, digest
from .cassette import RecordedCalls, make_llm
from .sandbox import MissingRecordedCall, ReplayBoundaryError, code_fingerprint, replay_sandbox


def audit_transitions(dataset: dict, jity_root: Path, run_dir: Path,
                      committed_outputs: bool = False, limit: int | None = None,
                      call_records=None) -> dict:
    """Stop at the first unavailable completion; never synthesize its response."""
    run_dir = Path(run_dir).resolve()
    jity_root = Path(jity_root).resolve()
    if run_dir == jity_root or jity_root in run_dir.parents:
        raise ValueError("状态回放目录不能位于 Jity 中")
    run_dir.mkdir(parents=True, exist_ok=False)
    summary = {"kind": "jity_transition_audit", "status": "running", "real_model_calls": 0,
               "committed_outputs": committed_outputs, "steps": [],
               "pipeline_scope": ["StoryOutputNormalizer", "SCORE.validate_output", "GameStateManager.apply_output",
                                  "MemoryLifecycleMixin._feed_memory", "MemoryController.maintain"],
               "not_replayed": ["ScenarioGenerator.generate", "Director", "campaign advancement", "original embedding transport"],
               "dataset_sha256": digest(dataset), "jity_source": code_fingerprint(jity_root)}
    atomic_json(run_dir / "inputs/dataset.json", dataset)
    calls = RecordedCalls(dataset.get("call_records", []) if call_records is None else call_records)
    atomic_json(run_dir / "inputs/calls.json", calls.records)
    atomic_json(run_dir / "result.json", summary)
    with replay_sandbox(jity_root, run_dir):
        from app.database import Database
        from app.services.game_state import GameStateManager
        from app.services.memory.memory_controller import MemoryController
        from app.services.scenario_generator.memory_lifecycle import MemoryLifecycleMixin

        db = Database(run_dir / "runtime.sqlite3")
        manager = GameStateManager(db)
        llm = make_llm(calls, run_dir)
        session_id = "offline-transition-audit"

        class Feed(MemoryLifecycleMixin):
            def _get_memory_controller(self, *args):
                return controller

            def _campaign_session_index(self, unused):
                return state.get("_campaign_session_index", 0)

        for index, turn in enumerate(dataset["turns"][:limit]):
            checkpoint = dataset["initial"] if index == 0 else dataset["turns"][index - 1]
            state = deepcopy(checkpoint["state"])
            before = digest(checkpoint)
            calls.checkpoint_turn = turn["turn"]
            controller = MemoryController(llm, db, session_id, embedding_client=None)
            if "_memory_controller" in state:
                controller.load_state(state["_memory_controller"])
            # Match ScenarioGenerator's controller initialization for legacy
            # snapshots too: inventory lifecycle states remain authoritative.
            controller.score_tracker.seed(state.get("items", []), int(state.get("turn", 0)))
            trace = {"turn": turn["turn"], "turn_id": turn["turn_id"], "backend_checkpoint_sha256": before,
                     "branch_policy": "independent_frozen_parent", "player_action": turn["player_action"],
                     "action_check": deepcopy(turn.get("action_check")), "real_model_calls": 0,
                     "source": turn.get("source"), "status": "running"}
            try:
                stored = turn.get("model_output") or {}
                if committed_outputs or turn.get("source") in {"scripted", "examiner_blocked", "opening"}:
                    # This is an explicit data-replay mode, never an exact-call substitute.
                    output = llm._parse_story_output(json.dumps(turn["output"], ensure_ascii=False))
                    trace["response_provenance"] = "normalized_committed_output"
                else:
                    prompt = stored.get("prompt_text")
                    if not prompt:
                        raise MissingRecordedCall("该回合缺失实际请求 prompt，无法逐调用严格回放")
                    output, _ = asyncio.run(llm.generate(prompt, model=stored.get("model"), purpose="story_narrator"))
                    trace["response_provenance"] = "exact_recorded_call"
                trace["parsed_historical_output"] = output.model_dump()
                # The historical die is authoritative; never roll a new die.
                output.action_check = output.__class__.model_validate(turn["output"]).action_check
                controller.score_tracker.validate_output(output, int(state.get("turn", 0)) + 1)
                trace["validated_output"] = output.model_dump()
                next_state = manager.apply_output(state, turn["player_action"], output)
                next_state["items"] = controller.score_tracker.reconcile_inventory(next_state.get("items", []))
                Feed()._feed_memory(session_id, next_state, output, turn["player_action"], None)
                trace["state_after_apply"] = deepcopy(next_state)
                trace["memory_after_write"] = controller.export_state()
                history = dataset["turns"][max(0, index - 9):index + 1]
                dialogues = "\n\n".join("[玩家]: %s\n[主持人]: %s" % (row["player_action"], json.dumps(row["output"], ensure_ascii=False)) for row in history)
                asyncio.run(controller.maintain(session_id, int(next_state.get("turn", 0)), dialogues=dialogues))
                next_state["_memory_controller"] = controller.export_state()
                trace["memory_after_maintenance"] = deepcopy(next_state["_memory_controller"])
                keys = ("sanity", "health", "turn", "current_location", "items", "npcs", "quests", "world_facts", "player_status")
                trace["state_comparison"] = {key: {"recomputed": next_state.get(key), "recorded": turn["state"].get(key)}
                                             for key in keys if next_state.get(key) != turn["state"].get(key)}
                # Persist only inside the evaluator's independent database.
                manager.save_state(session_id, "离线状态边界复核", "offline", next_state)
                trace["status"] = "audited"
            except ReplayBoundaryError as exc:
                trace.update(status="missing_call" if isinstance(exc, MissingRecordedCall) else "boundary_error", error=str(exc))
            except Exception as exc:
                trace.update(status="error", error="%s: %s" % (type(exc).__name__, exc))
            trace["parent_checkpoint_unchanged"] = digest(checkpoint) == before
            trace["calls"] = deepcopy([entry for entry in calls.events if entry["checkpoint_turn"] == turn["turn"]])
            path = "traces/turn-%04d.json" % turn["turn"]
            atomic_json(run_dir / path, trace)
            summary["steps"].append({"turn": turn["turn"], "status": trace["status"], "trace_path": path, "error": trace.get("error")})
            atomic_json(run_dir / "calls.json", calls.events)
            if trace["status"] != "audited":
                summary["status"] = "blocked_missing_record" if trace["status"] == "missing_call" else "error"
                break
        else:
            summary["status"] = "completed_boundary_audit"
        atomic_json(run_dir / "result.json", summary)
    return summary
