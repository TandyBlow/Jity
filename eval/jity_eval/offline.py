"""Deterministic fixture adapter; not a model or an implementation of Jity memory.

Gold labels are deliberately absent from this module's interface. These fixtures
exercise scheduling, visibility boundaries and evidence recording only.
"""
from __future__ import annotations

import copy
import json
from typing import Any


class OfflineSession:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.structured: dict[str, dict] = {}
        self.narrative: dict[str, dict] = {}
        self.truth: dict[str, dict] = {}
        self.actions: list[dict] = []

    def ingest(self, event: dict) -> None:
        self.events.append(copy.deepcopy(event))
        for fact in event["facts"]:
            record = {"id": fact["id"], "value": fact["value"], "source_turn": event["turn"]}
            self.truth[fact["id"]] = copy.deepcopy(record)
            if fact["storage"] in ("structured", "both"):
                self.structured[fact["id"]] = copy.deepcopy(record)
            if fact["storage"] in ("narrative", "both"):
                self.narrative[fact["id"]] = copy.deepcopy(record)

    def checkpoint(self) -> dict:
        return copy.deepcopy({
            "events": self.events, "structured": self.structured,
            "narrative": self.narrative, "truth": self.truth, "actions": self.actions,
        })

    @classmethod
    def fork(cls, checkpoint: dict) -> OfflineSession:
        instance = cls()
        data = copy.deepcopy(checkpoint)
        for key in ("events", "structured", "narrative", "truth", "actions"):
            setattr(instance, key, data[key])
        return instance

    def visible_context(self, mode: str, recent_window: int) -> dict:
        if mode not in ("full", "recent", "state"):
            raise ValueError("unsupported offline mode")
        recent = copy.deepcopy(self.events[-recent_window:])
        facts = {}
        candidates = []
        if mode in ("full", "state"):
            candidates.extend(self.structured.values())
        if mode == "full":
            candidates.extend(self.narrative.values())
        for event in recent:
            candidates.extend({"id": f["id"], "value": f["value"], "source_turn": event["turn"]}
                              for f in event["facts"])
        for fact in sorted(candidates, key=lambda f: f["source_turn"]):
            facts[fact["id"]] = copy.deepcopy(fact)
        channels = ["recent_history"]
        if mode in ("full", "state"):
            channels.append("structured_fixture")
        if mode == "full":
            channels.append("narrative_fixture")
        return {"mode": mode, "channels_applied": channels, "recent_history": recent,
                "visible_facts": list(facts.values()), "adapter": "offline"}

    def probe(self, probe: dict, mode: str, recent_window: int) -> dict:
        context = self.visible_context(mode, recent_window)
        # The mock can only look in the allowed view. It cannot read self.truth
        # or a gold answer while producing a response.
        hit = next((f for f in context["visible_facts"] if f["id"] == probe["fact_id"]), None)
        value = hit["value"] if hit else None
        decision = ("use_fact" if hit else "ask_for_information") if probe["kind"] == "action" else ("answer" if hit else "abstain")
        draft = {"value": value, "decision": decision, "evidence_turn": hit["source_turn"] if hit else None}
        if probe["kind"] == "action":
            self.actions.append(copy.deepcopy(draft))
        return {
            "simulation": True, "real_model_calls": 0,
            "visible_context": context, "probe_input": copy.deepcopy(probe),
            "raw_response": json.dumps(draft, ensure_ascii=False),
            "parsed_draft": copy.deepcopy(draft), "validated_output": copy.deepcopy(draft),
            "validation": {"implementation": "offline_identity_stub", "applied": False},
            "committed_state": {"actions": copy.deepcopy(self.actions)},
            "backend_truth": copy.deepcopy(self.truth),
            "limitations": "离线字典模拟；不调用 Jity、真实模型、摘要、向量检索或 SCORE 规则。",
        }


def grade(draft: dict, expected_value: str | None, kind: str) -> dict:
    """Strict mechanical grading, separate from the adapter and its visible view."""
    if not isinstance(draft, dict) or "value" not in draft or "decision" not in draft:
        raise ValueError("invalid response shape; cannot grade")
    if draft["value"] is not None and not isinstance(draft["value"], str):
        raise ValueError("response value must be string or null")
    expected_decision = ("use_fact" if expected_value is not None else "ask_for_information") if kind == "action" else ("answer" if expected_value is not None else "abstain")
    correct = draft["value"] == expected_value and draft["decision"] == expected_decision
    return {"status": "passed" if correct else "failed", "correct": correct,
            "expected_value": expected_value, "actual_value": draft["value"],
            "expected_decision": expected_decision, "actual_decision": draft["decision"],
            "method": "offline_exact_value_and_decision", "is_model_evaluation": False}
