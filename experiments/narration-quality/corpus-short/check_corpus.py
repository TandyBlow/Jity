#!/usr/bin/env python3
"""Structural checks for the short-scene corpus.

This script does not judge prose quality or semantic fact coverage. It checks
that every frozen row keeps its input intact, that derived rows differ only in a
documented time advance, that authored product-world rows carry the world-file
identity and a state result matching their delta, that all material is marked as
training material, and that every row carries the metadata a consumer needs.
Fact coverage is checked by hand in review.md.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import pathlib
import re
import sys
from collections import Counter

DEFAULT_SOURCE_ROOT = pathlib.Path(
    "D:/others/Jity/.local/world-components-worktree/experiments/world-components/narration-dataset-v1"
)
SOURCE_COMMIT = "1ab6ca791f97529a7bffed1f4837bf81a28badcb"
AUTHORED_DATASET = "dragon-raja-free-day"
AUTHORED_COMMIT = "865ae64e0901a70c3db4f1d0eb2af60268943c53"
AUTHORED_FILE = "frontend/public/worlds/dragon-raja-free-day.world.json"
AUTHORED_WORLD_SHA256 = "0a8b63be2932ceb5d597adf332123d8cfb584c2fd92ddd351770d4a9fa09f24a"
WORKTREE_ROOT = pathlib.Path(__file__).resolve().parent.parents[2]
MIN_CHARS = 60
MAX_CHARS = 160
CHINESE_DIGITS = "零一二三四五六七八九"
POSTURE_PATTERN = re.compile(
    r"(站在|站着|坐着|蹲在|蹲下|蹲着|躺在|躺着|跪着|靠在|靠着|坐下|站起|起身)"
)
KNOWN_CATEGORIES = {
    "no_change",
    "movement",
    "separation",
    "item_change",
    "location_change",
    "appearance_change",
    "personality_change",
    "secret_reveal",
    "task_complete",
    "task_added",
    "sanity_change",
}


def canonical(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fail(errors: list[str], message: str) -> None:
    errors.append(message)



def chinese_minutes(count: int) -> str:
    if count < 10:
        return ("两" if count == 2 else CHINESE_DIGITS[count]) + "分钟"
    if count < 20:
        suffix = CHINESE_DIGITS[count % 10] if count % 10 else ""
        return "十" + suffix + "分钟"
    tens, ones = divmod(count, 10)
    suffix = CHINESE_DIGITS[ones] if ones else ""
    return CHINESE_DIGITS[tens] + "十" + suffix + "分钟"


def check_time_stated(errors: list[str], label: str, record: dict[str, object]) -> None:
    advance = record["input"]["本回合变化"]["时间推进"]
    match = re.match(r"(\d+)\s*分钟", advance)
    if not match:
        fail(errors, f"{label}: unreadable time advance {advance!r}")
        return
    phrase = chinese_minutes(int(match.group(1)))
    if phrase not in record["targetText"]:
        fail(errors, f"{label}: targetText does not state the time advance {phrase!r}")


def load_world_names(world_path: pathlib.Path) -> set[str]:
    world = json.load(io.open(world_path, encoding="utf-8"))
    initial = world["initial"]
    names: set[str] = set()
    for section in ("locations", "characters", "items"):
        for entry in initial[section].values():
            name = entry.get("name")
            if name:
                names.add(name)
    return names


def check_no_posture(errors: list[str], label: str, record: dict[str, object]) -> None:
    licensed = json.dumps(record["input"], ensure_ascii=False)
    for match in POSTURE_PATTERN.finditer(record["targetText"]):
        word = match.group(0)
        if word in licensed:
            continue
        fail(errors, f"{label}: targetText claims an unsettled posture: {word!r}")
        return


def check_authored_entities(
    errors: list[str], label: str, record: dict[str, object], world_names: set[str]
) -> None:
    licensed = json.dumps(record["input"], ensure_ascii=False)
    for name in sorted(world_names, key=len, reverse=True):
        if name in licensed:
            continue
        if name in record["targetText"]:
            fail(errors, f"{label}: entity {name!r} appears in targetText but is not licensed by the input")


def task_by_goal(tasks: dict[str, object], goal: str) -> dict[str, object] | None:
    if tasks.get("大任务", {}).get("目标") == goal:
        return tasks["大任务"]
    for child in tasks.get("小任务", []):
        if child.get("目标") == goal:
            return child
    return None


def check_authored_state(errors: list[str], label: str, record: dict[str, object]) -> None:
    state = record["input"]["本回合状态"]
    delta = record["input"]["本回合变化"].get("变化", {})
    for name, change in delta.items():
        if "人物" in state and name in state["人物"]:
            after = state["人物"][name]
            if "位置" in change and after.get("位置") != change["位置"]:
                fail(errors, f"{label}: 人物 {name} 的位置结果不匹配")
            if "精神值" in change and after.get("精神值") != change["精神值"]:
                fail(errors, f"{label}: 人物 {name} 的精神值结果不匹配")
            if "新增外貌" in change or "解除外貌" in change:
                for item in change.get("新增外貌", []):
                    if item not in after.get("外貌", []):
                        fail(errors, f"{label}: 人物 {name} 缺少新增外貌 {item!r}")
                for item in change.get("解除外貌", []):
                    if item in after.get("外貌", []):
                        fail(errors, f"{label}: 人物 {name} 仍保留解除外貌 {item!r}")
            if "新增个性" in change:
                for item in change["新增个性"]:
                    if item not in after.get("个性", []):
                        fail(errors, f"{label}: 人物 {name} 缺少新增个性 {item!r}")
            if "完成任务" in change or "新增小任务" in change:
                tasks = after.get("任务", {})
                for goal in change.get("完成任务", []):
                    task = task_by_goal(tasks, goal)
                    if task is None or task.get("状态") != "已完成":
                        fail(errors, f"{label}: 人物 {name} 完成任务未在结果状态中完成: {goal}")
                for new_task in change.get("新增小任务", []):
                    task = task_by_goal(tasks, new_task["目标"])
                    if task is None or task.get("状态") != new_task.get("状态", "未完成"):
                        fail(errors, f"{label}: 人物 {name} 新增任务未在结果状态中匹配: {new_task['目标']}")
        elif "物品" in state and name in state["物品"]:
            after = state["物品"][name]
            if "位置" in change and after.get("位置") != change["位置"]:
                fail(errors, f"{label}: 物品 {name} 的位置结果不匹配")
            if "新增外貌" in change or "解除外貌" in change:
                for item in change.get("新增外貌", []):
                    if item not in after.get("外貌", []):
                        fail(errors, f"{label}: 物品 {name} 缺少新增外貌 {item!r}")
                for item in change.get("解除外貌", []):
                    if item in after.get("外貌", []):
                        fail(errors, f"{label}: 物品 {name} 仍保留解除外貌 {item!r}")
        elif "地点" in state and name in state["地点"]:
            after = state["地点"][name]
            for item in change.get("新增外貌", []):
                if item not in after.get("外貌", []):
                    fail(errors, f"{label}: 地点 {name} 缺少新增外貌 {item!r}")
            for item in change.get("解除外貌", []):
                if item in after.get("外貌", []):
                    fail(errors, f"{label}: 地点 {name} 仍保留解除外貌 {item!r}")
        else:
            fail(errors, f"{label}: 变化目标 {name} 不在本回合状态中")
    if record.get("variant") == "sanity-literal":
        text = record["targetText"]
        if "43" not in text or "35" not in text:
            fail(errors, f"{label}: sanity-literal target must contain both 43 and 35")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", default=str(pathlib.Path(__file__).with_name("rows.jsonl")))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    args = parser.parse_args()

    rows_path = pathlib.Path(args.rows)
    source_root = pathlib.Path(args.source_root)
    source_rows_path = source_root / "rows-xy.jsonl"
    splits_path = source_root / "splits" / "v1.json"
    world_path = WORKTREE_ROOT / AUTHORED_FILE

    for path in (rows_path, source_rows_path, splits_path, world_path):
        if not path.exists():
            print(f"missing required file: {path}", file=sys.stderr)
            return 2
    world_sha = hashlib.sha256(world_path.read_bytes()).hexdigest()
    if world_sha != AUTHORED_WORLD_SHA256:
        print(f"authored world SHA mismatch: {world_sha}", file=sys.stderr)
        return 2
    world_names = load_world_names(world_path)

    raw = rows_path.read_text(encoding="utf-8")
    if "\r" in raw:
        print("rows.jsonl contains CR; expected LF", file=sys.stderr)
        return 2

    source_rows = {
        item["id"]: item
        for item in (json.loads(line) for line in io.open(source_rows_path, encoding="utf-8") if line.strip())
    }
    splits = json.load(io.open(splits_path, encoding="utf-8"))
    split_of = {rid: name for name, ids in splits.items() for rid in ids}

    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    derived_sources: set[str] = set()
    family_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    lengths: list[int] = []
    authored_count = 0
    frozen_count = 0

    required_fields = {
        "id",
        "sourceRowId",
        "sourceEvidence",
        "sourceSplit",
        "sourceInputSha256",
        "worldFamily",
        "categories",
        "input",
        "targetText",
        "targetChars",
        "requiredFacts",
        "licensedDetails",
        "knowledgeBoundary",
        "forbiddenInventions",
        "styleReferenceIds",
    }

    for index, record in enumerate(records, start=1):
        label = f"row {index} ({record.get('id', '?')})"
        missing = required_fields - set(record)
        if missing:
            fail(errors, f"{label}: missing fields {sorted(missing)}")
            continue

        rid = record["id"]
        source_id = record["sourceRowId"]
        if rid in seen_ids:
            fail(errors, f"{label}: duplicate id {rid}")
        seen_ids.add(rid)
        is_derived = record.get("sourceEvidence", {}).get("derived") is True
        if source_id in seen_sources:
            if not is_derived:
                fail(errors, f"{label}: duplicate sourceRowId {source_id}")
            elif source_id in derived_sources:
                fail(errors, f"{label}: duplicate derived row for sourceRowId {source_id}")
        seen_sources.add(source_id)
        if is_derived:
            derived_sources.add(source_id)

        evidence = record["sourceEvidence"]
        is_authored = source_id.startswith("authored:")
        if is_authored:
            authored_count += 1
            if not source_id.startswith("authored:dragon-raja-free-day#"):
                fail(errors, f"{label}: authored sourceRowId has an unexpected namespace")
            if record["sourceSplit"] != "train":
                fail(errors, f"{label}: authored split must be train")
            if evidence.get("authored") is not True:
                fail(errors, f"{label}: authored evidence needs authored=true")
            if evidence.get("dataset") != AUTHORED_DATASET:
                fail(errors, f"{label}: authored dataset mismatch")
            if evidence.get("sourceFile") != AUTHORED_FILE:
                fail(errors, f"{label}: authored sourceFile mismatch")
            if evidence.get("sourceCommit") != AUTHORED_COMMIT:
                fail(errors, f"{label}: authored sourceCommit mismatch")
            if evidence.get("worldSha256") != AUTHORED_WORLD_SHA256:
                fail(errors, f"{label}: authored worldSha256 mismatch")
            if not evidence.get("premise"):
                fail(errors, f"{label}: authored evidence needs a premise")
            if evidence.get("split") != "train":
                fail(errors, f"{label}: authored sourceEvidence.split must be train")
            expected_hash = hashlib.sha256(canonical(record["input"]).encode("utf-8")).hexdigest()
            if "variant" in record and record["variant"] not in ("sanity-literal",):
                fail(errors, f"{label}: unknown authored variant {record['variant']!r}")
            check_authored_state(errors, label, record)
            check_authored_entities(errors, label, record, world_names)
        else:
            frozen_count += 1
            if source_id not in source_rows:
                fail(errors, f"{label}: sourceRowId {source_id} not in frozen rows")
                continue
            if split_of.get(source_id) != "train" or record["sourceSplit"] != "train":
                fail(errors, f"{label}: split must be train, got {split_of.get(source_id)!r}/{record['sourceSplit']!r}")
            if evidence.get("rowId") != source_id:
                fail(errors, f"{label}: sourceEvidence.rowId != sourceRowId")
            if evidence.get("split") != "train":
                fail(errors, f"{label}: sourceEvidence.split must be train")
            if evidence.get("sourceCommit") != SOURCE_COMMIT:
                fail(errors, f"{label}: sourceEvidence.sourceCommit mismatch")

            source_input = source_rows[source_id]["x"]
            derived = evidence.get("derived") is True
            if derived:
                if evidence.get("baseRowId") != source_id:
                    fail(errors, f"{label}: derived row baseRowId must equal sourceRowId")
                if not evidence.get("derivation"):
                    fail(errors, f"{label}: derived row needs a derivation note")
                expected_input = copy.deepcopy(source_input)
                expected_input["本回合变化"]["时间推进"] = record["input"]["本回合变化"]["时间推进"]
                if record["input"] != expected_input:
                    fail(errors, f"{label}: derived input must differ from the base only in time advance")
                expected_hash = hashlib.sha256(canonical(record["input"]).encode("utf-8")).hexdigest()
            else:
                if record["input"] != source_input:
                    fail(errors, f"{label}: input differs from frozen x")
                expected_hash = hashlib.sha256(canonical(source_input).encode("utf-8")).hexdigest()
        if record["sourceInputSha256"] != expected_hash:
            fail(errors, f"{label}: sourceInputSha256 mismatch")

        text = record["targetText"]
        length = len(text)
        lengths.append(length)
        if record["targetChars"] != length:
            fail(errors, f"{label}: targetChars says {record['targetChars']}, actual {length}")
        if not (MIN_CHARS <= length <= MAX_CHARS):
            fail(errors, f"{label}: targetText length {length} outside {MIN_CHARS}-{MAX_CHARS}")
        if "\n" in text or "\r" in text:
            fail(errors, f"{label}: targetText must be one paragraph")
        if text != text.strip():
            fail(errors, f"{label}: targetText has leading/trailing whitespace")
        if any(marker in text for marker in ("TODO", "待补", "……")):
            fail(errors, f"{label}: targetText contains a placeholder marker")

        if not record["requiredFacts"]:
            fail(errors, f"{label}: requiredFacts is empty")
        if not record["licensedDetails"]:
            fail(errors, f"{label}: licensedDetails is empty")
        boundary = record["knowledgeBoundary"]
        for key in ("viewpoint", "canKnow", "mustNotReveal"):
            if key not in boundary:
                fail(errors, f"{label}: knowledgeBoundary missing {key}")
        if not record["forbiddenInventions"]:
            fail(errors, f"{label}: forbiddenInventions is empty")

        check_no_posture(errors, label, record)
        check_time_stated(errors, label, record)

        cats = set(record["categories"])
        unknown = cats - KNOWN_CATEGORIES
        if unknown:
            fail(errors, f"{label}: unknown categories {sorted(unknown)}")
        family = record["worldFamily"]
        if not family:
            fail(errors, f"{label}: worldFamily is empty")
        family_counts[family] += 1
        for cat in cats:
            category_counts[cat] += 1

        for ref in record["styleReferenceIds"]:
            if ref not in source_rows:
                fail(errors, f"{label}: styleReferenceId {ref} not in frozen rows")

    print(f"rows: {len(records)}")
    print(f"frozen rows: {frozen_count}; authored rows: {authored_count}")
    derived_count = sum(1 for r in records if r.get("sourceEvidence", {}).get("derived") is True)
    print(f"derived rows: {derived_count}")
    print(f"length: min={min(lengths) if lengths else 0} max={max(lengths) if lengths else 0}")
    length_buckets: Counter[str] = Counter(
        "60-79" if n < 80 else "80-119" if n < 120 else "120-160" for n in lengths
    )
    print("length buckets:", dict(sorted(length_buckets.items())))
    print("world families:", dict(sorted(family_counts.items())))
    print("categories:", dict(sorted(category_counts.items())))
    if errors:
        print("\nFAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("OK: structure, frozen/authored provenance, train-only split and length bounds pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
