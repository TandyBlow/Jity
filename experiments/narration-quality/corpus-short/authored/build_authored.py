#!/usr/bin/env python3
"""Build the authored short scenes and merge them into rows.jsonl.

The frozen 199-row dataset is read-only. Every authored row starts from the
browser world file's initial snapshot, applies exactly one authored delta, and
records the partial after-state that the delta licenses. The script keeps the
existing frozen rows byte-for-byte; it only replaces rows whose source is the
authored world, so rerunning is deterministic.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import pathlib
import re
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORLD_PATH = ROOT / "frontend/public/worlds/dragon-raja-free-day.world.json"
SCENES_PATH = HERE / "scenes.json"
AUTHORED_PATH = HERE.parent / "rows-authored.jsonl"
ROWS_PATH = HERE.parent / "rows.jsonl"

STATUS = {"pending": "未完成", "achieved": "已完成"}


def canonical(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def split_clauses(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[；。]", text) if part.strip()]


def status(value: str) -> str:
    return STATUS.get(value, value)


def root_task(character: dict[str, Any]) -> dict[str, Any]:
    tasks = character["tasks"]
    return next(task for task in tasks.values() if task["parentTaskId"] is None)


def child_tasks(character: dict[str, Any], goals: list[str] | None) -> list[dict[str, Any]]:
    tasks = character["tasks"]
    root_id = root_task(character)["id"]
    if goals is not None:
        children = [task for task in tasks.values() if task["id"] in goals]
    else:
        children = [task for task in tasks.values() if task["parentTaskId"] == root_id]
    return children


def task_block(character: dict[str, Any], goals: list[str] | None) -> dict[str, Any]:
    root = root_task(character)
    block: dict[str, Any] = {
        "大任务": {"目标": root["goal"], "状态": status(root["status"])}
    }
    children = child_tasks(character, goals)
    if children:
        block["小任务"] = [{"目标": child["goal"], "状态": status(child["status"])} for child in children]
    else:
        block["小任务"] = []
    return block


def character_input(world: dict[str, Any], cid: str, goals: list[str] | None, overrides: dict[str, Any]) -> dict[str, Any]:
    source = world["initial"]["characters"][cid]
    position = source.get("initialPosition") or {}
    container = position.get("containerId")
    location = world["initial"]["locations"].get(container, {}).get("name") or container
    result: dict[str, Any] = {
        "位置": location,
        "精神值": source["initialSanity"],
        "外貌": split_clauses(source["initialAppearance"]),
        "个性": split_clauses(source["initialPersonality"]),
        "任务": task_block(source, goals),
    }
    result.update(copy.deepcopy(overrides))
    return result


def item_input(world: dict[str, Any], iid: str, overrides: dict[str, Any]) -> dict[str, Any]:
    source = world["initial"]["items"][iid]
    position = source.get("initialPosition") or {}
    container = position.get("containerId")
    if container in world["initial"]["characters"]:
        place = world["initial"]["characters"][container]["name"]
    elif container in world["initial"]["items"]:
        place = world["initial"]["items"][container]["name"]
    else:
        place = world["initial"]["locations"].get(container, {}).get("name") or container
    result: dict[str, Any] = {
        "位置": place,
        "外貌": split_clauses(source.get("initialAppearance", "")),
    }
    result.update(copy.deepcopy(overrides))
    return result


def location_input(world: dict[str, Any], lid: str) -> dict[str, Any]:
    source = world["initial"]["locations"][lid]
    parent = source.get("parentLocationId")
    parent_name = world["initial"]["locations"].get(parent, {}).get("name") if parent else None
    return {"位于": parent_name, "外貌": [source.get("initialAppearance", "")]}


def find_task(target: dict[str, Any], goal: str) -> dict[str, Any] | None:
    tasks = target["任务"]
    if tasks["大任务"]["目标"] == goal:
        return tasks["大任务"]
    return next((child for child in tasks.get("小任务", []) if child["目标"] == goal), None)


def apply_character(target: dict[str, Any], delta: dict[str, Any]) -> None:
    if "位置" in delta:
        target["位置"] = delta["位置"]
    if "精神值" in delta:
        target["精神值"] = delta["精神值"]
    for field, key in (("外貌", "外貌"), ("个性", "个性")):
        values = target.setdefault(key, [])
        for removed in delta.get(f"解除{field}", []):
            if removed not in values:
                raise ValueError(f"cannot remove missing {field} item: {removed}")
            values.remove(removed)
        for added in delta.get(f"新增{field}", []):
            if added not in values:
                values.append(added)
    for goal in delta.get("完成任务", []):
        task = find_task(target, goal)
        if task is None:
            raise ValueError(f"cannot complete missing task: {goal}")
        task["状态"] = "已完成"
    for new_task in delta.get("新增小任务", []):
        target["任务"].setdefault("小任务", []).append({
            "目标": new_task["目标"],
            "状态": new_task.get("状态", "未完成"),
        })


def apply_item(target: dict[str, Any], delta: dict[str, Any]) -> None:
    if "位置" in delta:
        target["位置"] = delta["位置"]
    values = target.setdefault("外貌", [])
    for removed in delta.get("解除外貌", []):
        if removed not in values:
            raise ValueError(f"cannot remove missing item appearance: {removed}")
        values.remove(removed)
    for added in delta.get("新增外貌", []):
        if added not in values:
            values.append(added)


def apply_location(target: dict[str, Any], delta: dict[str, Any]) -> None:
    values = target.setdefault("外貌", [])
    for removed in delta.get("解除外貌", []):
        if removed not in values:
            raise ValueError(f"cannot remove missing location appearance: {removed}")
        values.remove(removed)
    for added in delta.get("新增外貌", []):
        if added not in values:
            values.append(added)


def build_row(world: dict[str, Any], scene: dict[str, Any], world_meta: dict[str, Any]) -> dict[str, Any]:
    before_locations = {
        world["initial"]["locations"][lid]["name"]: location_input(world, lid)
        for lid in scene["locations"]
    }
    before_characters = {}
    for cid in scene["characters"]:
        name = world["initial"]["characters"][cid]["name"]
        before_characters[name] = character_input(
            world,
            cid,
            scene.get("taskGoals", []) if cid == scene["viewpointId"] else [],
            scene.get("beforeOverrides", {}).get("characters", {}).get(cid, {}),
        )
    before_items = {}
    for iid in scene["items"]:
        name = world["initial"]["items"][iid]["name"]
        before_items[name] = item_input(
            world,
            iid,
            scene.get("beforeOverrides", {}).get("items", {}).get(iid, {}),
        )

    before = {"地点": before_locations, "人物": before_characters, "物品": before_items}
    after_state = copy.deepcopy(before)
    for name, delta in scene.get("delta", {}).items():
        if name in after_state["人物"]:
            apply_character(after_state["人物"][name], delta)
        elif name in after_state["物品"]:
            apply_item(after_state["物品"][name], delta)
        elif name in after_state["地点"]:
            apply_location(after_state["地点"][name], delta)
        else:
            raise ValueError(f"{scene['id']}: delta target not in before state: {name}")

    after: dict[str, Any] = {}
    for name, delta in scene.get("delta", {}).items():
        changed: dict[str, Any] = {}
        if "位置" in delta:
            changed["位置"] = after_state["人物"].get(name, after_state["物品"].get(name))["位置"]
        if "精神值" in delta:
            changed["精神值"] = after_state["人物"][name]["精神值"]
        if "新增外貌" in delta or "解除外貌" in delta:
            holder = after_state["人物"].get(name) or after_state["物品"].get(name) or after_state["地点"][name]
            changed["外貌"] = holder["外貌"]
        if "新增个性" in delta:
            changed["个性"] = after_state["人物"][name]["个性"]
        if "完成任务" in delta or "新增小任务" in delta:
            changed["任务"] = after_state["人物"][name]["任务"]
        if changed:
            after[name] = changed
    for name, override in scene.get("afterOverride", {}).items():
        after[name] = copy.deepcopy(override)

    viewpoint = world["initial"]["characters"][scene["viewpointId"]]["name"]
    input_obj = {
        "视角": f"主角视角（{viewpoint}）；只表达已结算的世界事实",
        "上回合状态": before,
        "本回合变化": {"时间推进": scene["time"], "变化": scene.get("delta", {})},
        "本回合状态": after,
    }

    record = {
        "id": scene["id"],
        "sourceRowId": scene["sourceRowId"],
        "sourceEvidence": {
            "dataset": world_meta["dataset"],
            "sourceCommit": world_meta["sourceCommit"],
            "sourceFile": world_meta["sourceFile"],
            "worldSha256": world_meta["worldSha256"],
            "premise": world_meta["premise"],
            "authored": True,
            "split": "train",
        },
        "sourceSplit": "train",
        "sourceInputSha256": hashlib.sha256(canonical(input_obj).encode("utf-8")).hexdigest(),
        "worldFamily": scene["worldFamily"],
        "categories": scene["categories"],
        "sequenceId": None,
        "turnIndex": None,
        "input": input_obj,
        "targetText": scene["targetText"],
        "targetChars": len(scene["targetText"]),
        "requiredFacts": scene["requiredFacts"],
        "licensedDetails": scene["licensedDetails"],
        "knowledgeBoundary": scene["knowledgeBoundary"],
        "forbiddenInventions": scene["forbiddenInventions"],
        "styleReferenceIds": scene["styleReferenceIds"],
        "notes": scene["notes"],
        "reviewState": scene["reviewState"],
    }
    if scene.get("variant"):
        record["variant"] = scene["variant"]
    return record


def main() -> int:
    scenes_doc = json.load(io.open(SCENES_PATH, encoding="utf-8"))
    world = json.load(io.open(WORLD_PATH, encoding="utf-8"))
    world_bytes = WORLD_PATH.read_bytes()
    actual_sha = hashlib.sha256(world_bytes).hexdigest()
    if actual_sha != scenes_doc["world"]["worldSha256"]:
        raise SystemExit(f"world SHA mismatch: {actual_sha} != {scenes_doc['world']['worldSha256']}")

    rows = [build_row(world, scene, scenes_doc["world"]) for scene in scenes_doc["scenes"]]
    with io.open(AUTHORED_PATH, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    existing_raw = ROWS_PATH.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    authored_dataset = scenes_doc["world"]["dataset"]
    for line in existing_raw:
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("sourceEvidence", {}).get("dataset") == authored_dataset:
            continue
        kept.append(line)
    with io.open(ROWS_PATH, "w", encoding="utf-8", newline="\n") as handle:
        for line in kept:
            handle.write(line + "\n")
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"authored rows: {len(rows)}")
    print(f"rows.jsonl: {len(kept)} frozen + {len(rows)} authored = {len(kept) + len(rows)}")
    for row in rows:
        print(f"{row['id']}: {row['targetChars']} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
