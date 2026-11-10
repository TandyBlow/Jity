# -*- coding: utf-8 -*-
"""Build (settled-fact draft -> prose) pairs with explicit, grouped splits.

The product page already produces a deterministic fact draft when a model's
prose is rejected. The integrator's request is exactly this shape: give the
model the draft, ask for prose, and train it to add nothing.

Inputs (all read-only):
  * data/rows-short-v1.jsonl    lane 01 hand-written short scenes (imported)
  * data/beats-v1.jsonl         beat prompts/scene metadata
  * data/beats-teacher-kept-v1.jsonl  graded teacher beats
  * optional: data/rows-v2.jsonl (199 frozen scenes, keeps frozen v1 splits)
  * optional: data/world-targets-v1.jsonl (lane-10 authored product-world targets)

Output row:
  {"id","split","mode","draft","user","target","weight","source"}

Split rule (evidence isolation):
  * the frozen 199 rows keep `splits/v1.json` unchanged;
  * teacher beats follow the frozen split of their source row;
  * lane-01 rows are grouped by (worldFamily, lineage) and the WHOLE group is
    assigned by a hash of the group key, so variants/turns of one source never
    spread across train/dev/test.
The group manifest is written next to the data with its SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))

ROWS_V2 = os.path.join(V2, "data", "rows-v2.jsonl")
SHORT_ROWS = os.path.join(V2, "data", "rows-short-v1.jsonl")
WORLD_TARGETS = os.path.join(V2, "data", "world-targets-v1.jsonl")
BEATS = os.path.join(V2, "data", "beats-v1.jsonl")
TEACHER = os.path.join(V2, "data", "beats-teacher-kept-v1.jsonl")
SPLIT = os.path.abspath(os.path.join(
    REPO, "experiments", "world-components", "narration-dataset-v1", "splits", "v1.json"))

UNIT_CN = {"second": "秒", "minute": "分钟", "hour": "小时",
           "day": "天", "month": "个月", "year": "年"}


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def draft_line(fact: Dict[str, Any]) -> str:
    kind = fact["kind"]
    if kind == "moved":
        return f"{fact['name']}从{fact['from']}走到{fact['to']}。"
    if kind == "task_achieved":
        return f"{fact['name']}完成了「{fact['goal']}」。"
    if kind == "personality_changed":
        return f"{fact['name']}多了一条个性：{fact['text']}。"
    if kind == "sanity_changed":
        return f"{fact['name']}的精神值从{fact['from']}变成{fact['to']}。"
    if kind == "time":
        amount = fact.get("amount")
        unit = UNIT_CN.get(fact.get("unit") or "", "")
        return f"时间过去{amount}{unit}。"
    return ""


def render_draft(facts: List[Dict[str, Any]], time: Optional[Dict[str, Any]] = None) -> str:
    lines: List[str] = []
    for fact in facts:
        line = draft_line(fact)
        if line:
            lines.append(line)
    if time and time.get("amount"):
        lines.append(f"时间过去{time['amount']}{UNIT_CN[time['unit']]}。")
    return "".join(lines)


def scene_meta(x: Dict[str, Any]) -> Dict[str, Any]:
    """Place and present cast for the viewpoint, read from the row's state."""
    viewpoint = str(x.get("视角") or "")
    name = viewpoint.split("（")[-1].split("）")[0] if "（" in viewpoint else viewpoint
    people = ((x.get("上回合状态") or {}).get("人物") or {})
    mine = people.get(name) or {}
    place = mine.get("位置") or ""
    present = [person for person, value in people.items()
               if person != name and value.get("位置") == place]
    return {"viewpoint": name, "place": place, "present": present}


def user_text(draft: str, place: str, present: List[str], mode: str) -> str:
    lines = [f"【事实草稿】{draft or '这一回合没有结算出变化。'}"]
    if place:
        lines.append(f"【地点】{place}")
    others = [name for name in present if name]
    if others:
        lines.append(f"【在场】{'、'.join(others)}")
    if mode == "short":
        lines.append("【要求】把草稿改写成正文，三句以内。只写草稿里的事实；"
                     "不新增人物、对白、物品、动作、往事、数字，不解释情绪。")
    else:
        lines.append("【要求】把草稿改写成正文。只写草稿里的事实；"
                     "不新增人物、对白、物品、动作、往事、数字，不解释情绪。")
    lines.append("【正文】")
    return "\n".join(lines)


def group_key_for_short(row: Dict[str, Any]) -> str:
    family = row.get("worldFamily") or "unknown"
    lineage = str(row.get("sourceRowId") or row["id"]).split("#")[-1]
    return f"{family}#{lineage}"


def group_split(key: str) -> str:
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 10
    if bucket == 0:
        return "test"
    if bucket in (1, 2):
        return "dev"
    return "train"


def parse_time(value: Any) -> Optional[Dict[str, Any]]:
    """`本回合变化/时间推进` is '20分钟' or '20 分钟'; return amount/unit."""
    if not value:
        return None
    text = str(value).replace(" ", "")
    digits = ""
    for char in text:
        if char.isdigit():
            digits += char
        else:
            break
    if not digits:
        return None
    rest = text[len(digits):]
    for unit in ("小时", "分钟", "秒", "天", "个月", "年"):
        if rest.startswith(unit):
            key = {"小时": "hour", "分钟": "minute", "秒": "second",
                   "天": "day", "个月": "month", "年": "year"}[unit]
            return {"amount": int(digits), "unit": key}
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(V2, "data", "train-draft-v1.jsonl"))
    parser.add_argument("--short-weight", type=int, default=8)
    parser.add_argument("--world-weight", type=int, default=8)
    parser.add_argument("--scene-weight", type=int, default=1)
    parser.add_argument("--teacher-weight", type=int, default=1)
    parser.add_argument("--include-scenes", action="store_true")
    parser.add_argument("--include-world", action="store_true")
    parser.add_argument("--split-manifest", default=os.path.join(V2, "data", "splits-draft-v1.json"))
    args = parser.parse_args()

    with io.open(SPLIT, encoding="utf-8") as handle:
        frozen = json.load(handle)
    split_of = {row_id: name for name in ("train", "dev", "test")
                for row_id in frozen.get(name, [])}

    sys.path.insert(0, HERE)
    import narration_rules as R  # noqa: E402

    beats = {beat["id"]: beat for beat in read_jsonl(BEATS)}
    sources: Dict[str, str] = {}
    out: List[Dict[str, Any]] = []
    groups: Dict[str, List[str]] = {}

    if args.include_scenes:
        sources["rows-v2"] = sha256(ROWS_V2)
        for row in read_jsonl(ROWS_V2):
            facts = [f for f in R.build_facts(row["x"]) if f["kind"] in R.MANDATORY]
            meta = scene_meta(row["x"])
            draft = render_draft(facts)
            out.append({"id": row["id"], "split": split_of[row["id"]], "mode": "scene",
                        "draft": draft,
                        "user": user_text(draft, meta["place"], meta["present"], "scene"),
                        "target": row["y"], "weight": args.scene_weight,
                        "source": "rows-v2"})

    sources["rows-short-v1"] = sha256(SHORT_ROWS)
    for row in read_jsonl(SHORT_ROWS):
        facts = [f for f in R.build_facts(row["input"]) if f["kind"] in R.MANDATORY]
        time = (row["input"].get("本回合变化") or {}).get("时间推进")
        draft = render_draft(facts, parse_time(time))
        meta = scene_meta(row["input"])
        key = group_key_for_short(row)
        split = group_split(key)
        groups.setdefault(key, []).append(row["id"])
        out.append({"id": row["id"], "split": split, "mode": "short", "draft": draft,
                    "user": user_text(draft, meta["place"], meta["present"], "short"),
                    "target": row["target"], "weight": args.short_weight,
                    "source": "short-01"})

    if args.include_world and os.path.exists(WORLD_TARGETS):
        sources["world-targets"] = sha256(WORLD_TARGETS)
        for row in read_jsonl(WORLD_TARGETS):
            beat = beats[row["id"]]
            scene = beat["scene"]
            draft = render_draft([beat["fact"]], beat.get("time"))
            out.append({"id": row["id"], "split": row["split"], "mode": "short",
                        "draft": draft,
                        "user": user_text(draft, scene.get("location") or "",
                                          [n for n in scene.get("present") or []
                                           if n != beat["fact"]["name"]], "short"),
                        "target": row["target"], "weight": args.world_weight,
                        "source": "authored-world"})

    if os.path.exists(TEACHER):
        sources["teacher"] = sha256(TEACHER)
        for row in read_jsonl(TEACHER):
            beat = (beats.get(row.get("sourceId") or "") or beats.get(row["id"])
                    or beats.get(re.sub(r"-\d+$", "", row["id"])))
            if beat is None:
                continue
            source_row = row.get("sourceId") or ""
            split = split_of.get(source_row, "train")
            groups.setdefault(f"frozen#{source_row}", []).append(row["id"])
            draft = render_draft([beat["fact"]], beat.get("time"))
            out.append({"id": "t-" + row["id"], "split": split, "mode": "short",
                        "draft": draft,
                        "user": user_text(draft, beat["scene"].get("location") or "",
                                          [n for n in beat["scene"].get("present") or []
                                           if n != beat["fact"]["name"]], "short"),
                        "target": row["target"], "weight": args.teacher_weight,
                        "source": "teacher-beat:" + row["kind"]})

    manifest = {
        "version": "draft-splits-v1",
        "rule": ("lane-01 rows: group = worldFamily#lineage, the whole group is assigned by a hash "
                 "of the group key; teacher beats follow the frozen v1 split of their source row; "
                 "the frozen 199 scenes keep v1.json unchanged"),
        "groups": {key: {"split": group_split(key) if not key.startswith("frozen#") else
                         split_of.get(key.split("#", 1)[1], "train"), "rows": ids}
                   for key, ids in sorted(groups.items())},
        "counts": {},
    }
    for row in out:
        manifest["counts"][row["split"]] = manifest["counts"].get(row["split"], 0) + 1
    with io.open(args.split_manifest, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    split_manifest_sha = sha256(args.split_manifest)

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        for row in out:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    counts: Dict[str, int] = {}
    weighted: Dict[str, int] = {}
    for row in out:
        counts[row["split"]] = counts.get(row["split"], 0) + 1
        weighted[row["split"]] = weighted.get(row["split"], 0) + row["weight"]
    summary = {"rows": len(out), "sha256": sha256(args.out), "splits": counts,
               "weighted": weighted, "sources": sources, "out": args.out,
               "splitManifest": args.split_manifest,
               "splitManifestSha256": split_manifest_sha}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
