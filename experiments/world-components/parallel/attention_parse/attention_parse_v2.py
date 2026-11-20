"""v2 extractor: player utterance -> scoped attention targets.

v1 (attention_parse.py) answers "who/what"; v2 adds "which part of it" and
implements freeze/contract-v1.md:

  scope    object | position | appearance | task | part
  part     literal part word + partAnchored (committed text, freeze/anchors-v1.json)
  state    resolved | ambiguous | unresolved | none

Two behaviours go beyond the frozen A01-A10 labels and are registered as
extra probes in freeze/v2-extra-probes.json, reported separately:

  - a task-goal mention maps to {ownerId, scope: task} (contract §7);
  - a detected local request outside the part lexicon ("手背上的划痕") is
    conservatively `unresolved` with empty targets instead of widening to
    `object` (user request 2026-11-08: do not re-expand the attention range).

Entity/pronoun/descriptor matching is delegated to the v1 module so the two
rounds share one implementation of M1-M5; only the scope layer is new.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import attention_parse as v1

SCOPES = {"object", "position", "appearance", "task", "part"}

# Declared fixed lexicon (contract §4). Words outside it never become a part.
PART_LEXICON = [
    "表面", "盒盖", "袖口", "指节", "额头", "斗篷", "鞋底",
    "下摆", "柜门", "储物柜", "窗纸", "风铃", "檐角", "桅杆", "衣角",
]
TASK_CUES = ["任务", "目标", "做完", "完成", "办完", "进度"]
APPEARANCE_CUES = ["穿的", "穿", "样子", "外观", "打扮", "身上", "衣服"]
POSITION_CUES = ["在哪儿", "在哪", "哪里", "位置", "走到", "去了", "到了", "待在", "站在"]

DE_TAIL_RE = re.compile(r"的([\u4e00-\u9fa5]{1,3})")


def _occurrences(text: str, words: list[str]) -> list[tuple[str, int, int]]:
    hits: list[tuple[str, int, int]] = []
    for word in words:
        start = 0
        while word:
            index = text.find(word, start)
            if index < 0:
                break
            hits.append((word, index, index + len(word)))
            start = index + 1
    return sorted(hits, key=lambda item: (item[1], -(item[2] - item[1])))


def _owner_of(span: tuple[int, int], entity_spans: list[tuple[int, int, str]]) -> str | None:
    """Nearest entity span: overlapping > closest end before > closest start after."""
    start, end = span
    for s, e, entity_id in entity_spans:
        if s < end and start < e:
            return entity_id
    before = [item for item in entity_spans if item[1] <= start]
    if before:
        return max(before, key=lambda item: item[1])[2]
    after = [item for item in entity_spans if item[0] >= end]
    if after:
        return min(after, key=lambda item: item[0])[2]
    return None


def _anchor_texts(anchors_doc: dict, ref: str, entity_id: str) -> list[str]:
    source = anchors_doc["sources"].get(ref, {"anchors": []})
    return [anchor["text"] for anchor in source["anchors"] if anchor["entityId"] == entity_id]


def _goal_cues(roster: dict, entity_id: str) -> list[str]:
    return [
        entity["goal"]
        for entity in roster["entities"]
        if entity["kind"] == "task" and entity.get("ownerId") == entity_id
    ]



def _trim_function_tail(text: str) -> str:
    """'划痕还' -> '划痕'; keeps at least one character."""
    while len(text) > 1 and text[-1] in v1.FUNCTION_CHARS:
        text = text[:-1]
    return text if text and text[0] not in v1.FUNCTION_CHARS else ""


def _blocked_reason(base) -> str | None:
    if base.status == "ambiguous":
        vias = {match["via"] for match in base.matches if match["entityId"] in set(base.ambiguous_candidates)}
        if "pronoun_ambiguous" in vias or "pronoun_place" in vias:
            return "pronoun_multiple_antecedents"
        if "descriptor" in vias:
            return "descriptor_not_unique"
        return "shared_name_stem"
    if base.status == "unresolved":
        for mention in base.unresolved_mentions:
            if v1.NICKNAME_RE.fullmatch(mention):
                return "nickname_not_in_committed_record"
        return "pronoun_without_antecedent"
    if base.status == "none":
        return "no_attention_mention"
    return None

def parse(
    utterance: str,
    roster: dict,
    prior: str | None = None,
    anchors_doc: dict | None = None,
    world_ref: str | None = None,
) -> dict:
    text = re.sub(r"\s+", "", utterance or "")
    base = v1.parse(text, roster, prior)

    entities = {entity["entityId"]: entity for entity in roster["entities"]}
    if base.status != "resolved":
        return {
            "state": base.status,
            "targets": [],
            "ambiguousCandidates": base.ambiguous_candidates,
            "unresolvedMentions": base.unresolved_mentions,
            "reason": _blocked_reason(base),
            "traces": base.matches,
        }

    # Entity spans from the v1 matches; task entities become their owner + task scope.
    first_span: dict[str, tuple[int, int]] = {}
    surface: dict[str, str] = {}
    task_via_goal: dict[str, str] = {}
    for match in base.matches:
        entity_id = match["entityId"]
        entity = entities.get(entity_id) or {}
        if entity.get("kind") == "task":
            owner = entity.get("ownerId")
            if not owner:
                continue
            task_via_goal.setdefault(owner, match["surface"])
            entity_id = owner
        first_span.setdefault(entity_id, (match["start"], match["end"]))
        surface.setdefault(entity_id, match["surface"])

    entity_spans = [(start, end, entity_id) for entity_id, (start, end) in first_span.items()]

    part_spans = _occurrences(text, PART_LEXICON)
    task_spans = _occurrences(text, TASK_CUES)
    appearance_spans = _occurrences(text, APPEARANCE_CUES)
    position_spans = _occurrences(text, POSITION_CUES)

    # Goal text mentioned in the utterance also means "task scope for the owner".
    goal_spans: list[tuple[str, int, int, str]] = []
    for entity_id in first_span:
        for goal in _goal_cues(roster, entity_id):
            index = text.find(goal)
            if index >= 0:
                goal_spans.append((goal, index, index + len(goal), entity_id))

    scope_of: dict[str, dict] = {}
    scope_cue: dict[str, str] = {}

    def assign(scope: str, spans: list[tuple[str, int, int]], owner_hint: str | None = None) -> None:
        for word, start, end in spans:
            owner = owner_hint or _owner_of((start, end), entity_spans)
            if owner is None or owner in scope_of:
                continue
            scope_of[owner] = {"scope": scope}
            scope_cue[owner] = word

    assign("part", part_spans)
    assign("task", task_spans)
    assign("appearance", appearance_spans)
    assign("position", position_spans)
    for goal, start, end, owner in goal_spans:
        if owner not in scope_of:
            scope_of[owner] = {"scope": "task"}
            scope_cue[owner] = goal

    targets: list[dict] = []
    for entity_id in sorted(first_span, key=lambda key: first_span[key][0]):
        scope = scope_of.get(entity_id, {"scope": "object"})
        target = {
            "entityId": entity_id,
            "scope": scope["scope"],
            "surface": surface.get(entity_id),
            "scopeCue": scope_cue.get(entity_id),
        }
        entity = entities.get(entity_id) or {}
        if target["scope"] == "part":
            part = scope_cue[entity_id]
            anchored_texts = _anchor_texts(anchors_doc or {}, world_ref or "", entity_id)
            target["part"] = part
            target["partAnchored"] = any(part in anchor for anchor in anchored_texts)
        if task_via_goal.get(entity_id) and target["scope"] == "task":
            target["surface"] = task_via_goal[entity_id]
        targets.append(target)

    # Conservative guard: a "的<tail>" local request outside the lexicon must not
    # fall back to object (that would re-expand the range).
    if targets and all(target["scope"] == "object" for target in targets):
        known_surfaces = set(PART_LEXICON + TASK_CUES + APPEARANCE_CUES + POSITION_CUES)
        for match in DE_TAIL_RE.finditer(text):
            tail = _trim_function_tail(match.group(1))
            if not tail:
                continue
            if tail in known_surfaces or any(tail.startswith(cue) for cue in known_surfaces):
                continue
            if any(tail in entity.get("name", "") for entity in roster["entities"]):
                continue
            return {
                "state": "unresolved",
                "targets": [],
                "ambiguousCandidates": [],
                "unresolvedMentions": [tail],
                "reason": "part_outside_lexicon",
                "traces": base.matches,
            }

    return {
        "state": "resolved",
        "targets": targets,
        "ambiguousCandidates": [],
        "unresolvedMentions": [],
        "reason": None,
        "traces": base.matches,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="c1 attention-parse v2 (scoped targets)")
    parser.add_argument("--rosters", default="freeze/rosters.json")
    parser.add_argument("--anchors", default="freeze/anchors-v1.json")
    parser.add_argument("--samples", default="freeze/acceptance-v1.json")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    rosters = json.loads(Path(args.rosters).read_text(encoding="utf-8"))["rosters"]
    anchors = json.loads(Path(args.anchors).read_text(encoding="utf-8"))
    samples = json.loads(Path(args.samples).read_text(encoding="utf-8"))["samples"]
    rows = []
    for sample in samples:
        ref = sample["worldRef"]
        rows.append(
            {
                "sampleId": sample["sampleId"],
                "parsed": parse(sample["utterance"], rosters[ref], sample.get("priorNarration"), anchors, ref),
            }
        )
    text = json.dumps({"protocol": "c1-attention-granularity-v1", "rows": rows}, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
