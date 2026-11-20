"""Attention scope filter for N2 optional facts (contract §3 / §6).

Input: the committed fact bundle (freeze/facts-v1.json) and the scoped
targets from attention_parse_v2. Output: selected fact ids in bundle order
plus a per-fact decision with a reason, so a failure can be located.

Rules:
  - must facts are always selected, whatever the attention is;
  - forbidden / uncertain facts are never selected;
  - optional facts are selected only when a target matches entity + scope
    (+ part text for scope=part);
  - empty targets select no optional fact at all (never select-all).
"""

from __future__ import annotations

SCOPE_KINDS = {
    "position": {"moved", "positioned_at", "position_relative", "slot_changed"},
    "appearance": {"appearance_changed", "appearance_removed"},
    "task": {"task_achieved", "subtask_added"},
}
PART_KINDS = {"appearance_changed", "appearance_removed"}


def fact_text(fact: dict) -> str:
    return fact.get("text") or fact.get("goal") or ""


def matches(fact: dict, target: dict) -> bool:
    if fact.get("entityId") != target.get("entityId"):
        return False
    scope = target.get("scope")
    if scope == "object":
        return True
    if scope in SCOPE_KINDS:
        return fact.get("kind") in SCOPE_KINDS[scope]
    if scope == "part":
        if fact.get("kind") not in PART_KINDS:
            return False
        return bool(target.get("part")) and target["part"] in fact_text(fact)
    return False


def select(facts: list[dict], targets: list[dict]) -> dict:
    decisions: list[dict] = []
    selected: list[str] = []
    for fact in facts:
        authorization = fact.get("authorization")
        if authorization == "must":
            selected.append(fact["factId"])
            decisions.append({"factId": fact["factId"], "kept": True, "reason": "must_kept"})
            continue
        if authorization in {"forbidden", "uncertain"}:
            decisions.append({"factId": fact["factId"], "kept": False, "reason": f"authorization_{authorization}"})
            continue
        if not targets:
            decisions.append({"factId": fact["factId"], "kept": False, "reason": "empty_targets"})
            continue
        hit = next((target for target in targets if matches(fact, target)), None)
        if hit is None:
            entity_ids = sorted({target.get("entityId") for target in targets})
            decisions.append(
                {
                    "factId": fact["factId"],
                    "kept": False,
                    "reason": "out_of_scope",
                    "factEntityId": fact.get("entityId"),
                    "targetEntityIds": entity_ids,
                }
            )
            continue
        selected.append(fact["factId"])
        decisions.append(
            {
                "factId": fact["factId"],
                "kept": True,
                "reason": "in_scope",
                "scope": hit.get("scope"),
                "part": hit.get("part"),
            }
        )
    return {"selectedFactIds": selected, "decisions": decisions}
