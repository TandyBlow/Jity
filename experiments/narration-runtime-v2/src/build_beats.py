# -*- coding: utf-8 -*-
"""Build the beat-scoped narration prompts.

A *beat* is one committed fact plus the scene it happened in. The product
writes one beat per model call (2 sentences at most) and assembles the beats
into the turn's prose. This module builds those beat records and the exact
prompt used for both teacher generation and student training/inference, so the
shape cannot drift between the two.

Sources:
  * the 199 frozen library rows (`data/rows-v2.jsonl`, split preserved);
  * the product's static Dragon Raja world (read-only input), for the entities
    the browser actually narrates.

Nothing here writes product state or the world file.
"""

from __future__ import annotations

import io
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
_ROOTS = os.path.abspath(os.path.join(REPO, "..", "..", ".."))
WORLD = os.environ.get("JITY_WORLD") or os.path.join(
    _ROOTS, "world-narration-worktree", "frontend", "public", "worlds",
    "dragon-raja-free-day.world.json")
ROWS = os.path.join(ROOT, "data", "rows-v2.jsonl")
SPLIT = os.path.join(REPO, "experiments", "world-components",
                     "narration-dataset-v1", "splits", "v1.json")
OUT = os.path.join(ROOT, "data", "beats-v1.jsonl")

STYLE_LINE = "【写法】一到两句。只写这一拍的事，句子短，落在动作和物件上，不解释情绪。"
SYSTEM = ("你是中文小说作者，为一个文字冒险游戏写正文。文字要具体、克制，"
          "靠动作、环境和物件细节推进，不写标题，不复述设定。")

EXAMPLES = {
    "moved": ("诺诺从器材棚门外走进器材棚",
              "诺诺把枪口压低，从器材棚门外走进去，靴底碾过一层薄灰。"),
    "task_achieved": ("芬格尔完成了「把相机收进柜子」",
                      "芬格尔把相机塞进柜子，锁扣合上，这件事就算做完了。"),
    "personality_changed": ("苏茜的个性多了一条：愿意在交火里先开口",
                            "苏茜先开了口，声音不大，却没有再退。"),
    "sanity_changed": ("凯撒的精神值从60变成54",
                       "凯撒按住额角缓了一会儿，精神值落到54。"),
    "time": ("时间过去5分钟", "五分钟过去，回廊尽头始终没有脚步声。"),
}

WRITING = {
    "moved": "写这个人从旧位置走到新位置的过程；可以带一个环境细节；不要写别的事、别人的动作或对白。",
    "task_achieved": "写她做成这件事的结果或最后一个动作，让人看出这件事已经做完；不要写下一步，不要写别人。",
    "personality_changed": "用一个动作或一句短话表现这个变化；不要写别的场景、别人的事。",
    "sanity_changed": "写出精神数值的变化（两个数字都要出现），落在身体或感觉上；不要写别的场景。",
    "time": "写出这段时间过去了，落在环境或动作上；不要写新的事情发生。",
}

UNIT_CN = {"second": "秒", "minute": "分钟", "hour": "小时",
           "day": "天", "month": "个月", "year": "年"}


def load_rows() -> List[Dict[str, Any]]:
    with io.open(ROWS, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_split() -> Dict[str, List[str]]:
    with io.open(SPLIT, encoding="utf-8") as handle:
        raw = json.load(handle)
    return {key: list(value) for key, value in raw.items()}


def load_world() -> Dict[str, Any]:
    with io.open(WORLD, encoding="utf-8") as handle:
        return json.load(handle)


def viewpoint_name(视角: str) -> str:
    text = str(视角 or "")
    if "（" in text and "）" in text:
        return text.split("（", 1)[1].split("）", 1)[0].strip()
    return text.strip()


def clip(text: Any, limit: int = 70) -> str:
    value = str(text or "").replace("\n", " ").strip()
    return value if len(value) <= limit else value[:limit] + "…"


def place_line(before: Dict[str, Any], name: str) -> str:
    places = before.get("地点") or {}
    entry = places.get(name) or {}
    parent = entry.get("位于")
    look = "、".join(entry.get("外貌") or [])
    if parent:
        return f"{name}（在{parent}里）：{clip(look)}"
    return f"{name}：{clip(look)}" if look else name


def person_line(before: Dict[str, Any], name: str) -> str:
    person = (before.get("人物") or {}).get(name) or {}
    bits: List[str] = []
    if person.get("位置"):
        bits.append(f"在{person['位置']}")
    looks = person.get("外貌") or []
    if looks:
        bits.append("外貌" + "、".join(clip(item, 24) for item in looks[:2]))
    return f"{name}：{'，'.join(bits)}" if bits else name


def present_names(before: Dict[str, Any], location: Optional[str],
                  exclude: Iterable[str] = ()) -> List[str]:
    skip = set(exclude)
    names = []
    for name, person in (before.get("人物") or {}).items():
        if name in skip:
            continue
        if location is None or person.get("位置") == location:
            names.append(name)
    return names


def fact_phrase(fact: Dict[str, Any], natural: bool = True) -> str:
    kind = fact["kind"]
    if kind == "moved":
        return f"{fact['name']}从{fact['from']}走到{fact['to']}"
    if kind == "task_achieved":
        return f"{fact['name']}完成了「{fact['goal']}」"
    if kind == "personality_changed":
        return f"{fact['name']}的个性多了一条：{fact['text']}"
    if kind == "sanity_changed":
        return f"{fact['name']}的精神值从{fact['from']}变成{fact['to']}"
    raise ValueError(kind)


def beat_prompt(scene: Dict[str, Any], fact: Dict[str, Any],
                time: Optional[Dict[str, Any]] = None,
                literal: bool = False) -> str:
    """The one prompt shape shared by teacher, trainer and inference.

    The committed fact is stated first and the subject is named, because the
    failures observed on the pilot came from the model narrating the scene's
    viewpoint instead of the fact's subject. `literal=True` keeps the older
    gate-binding variant for comparison; the default teaches natural prose.
    """
    kind = "time" if fact["kind"] == "time" else fact["kind"]
    subject = scene["viewpoint"] if kind == "time" else fact["name"]
    lines: List[str] = []
    lines.append("【本拍事实】" + fact["phrase"])
    lines.append(f"【主体】{subject}：这一段的动作属于{subject}，不要换成别人。")
    where = scene["viewpoint"]
    if scene.get("location"):
        where += f"在{scene['location']}"
    lines.append(f"【场景】{where}")
    for line in scene.get("locationLines") or []:
        lines.append(f"　{line}")
    present = [name for name in scene.get("present") or [] if name != subject]
    if present:
        lines.append("【在场】" + "、".join(present) + "（只作为在场的人，不写他们的动作和对白）")
    if time:
        lines.append(f"【时间】{time['amount']}{UNIT_CN[time['unit']]}过去了")
    example_fact, example_text = EXAMPLES[kind]
    lines.append(f"【示例】事实：{example_fact}。正文：{example_text}")
    writing = WRITING[kind]
    if literal and fact["kind"] == "task_achieved":
        writing = "把「」里的任务原话一字不改地放进句子里，加上完成的动作或结果；不要写下一步，不要写别人。"
    if literal and fact["kind"] == "personality_changed":
        writing = "把「」里的个性原话一字不改地写进句子，用动作或一句话带出来；不要写别的场景。"
    if literal and fact["kind"] == "sanity_changed":
        writing = "写出精神值从多少变成多少，两个数字都要出现；不要写别的场景。"
    lines.append("【写法】一到两句。" + writing)
    lines.append("【正文】")
    return "".join(lines)


def library_beats(rows: List[Dict[str, Any]], split: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    split_of = {}
    for name in ("train", "dev", "test"):
        for row_id in split.get(name, []):
            split_of[row_id] = name
    beats: List[Dict[str, Any]] = []
    for row in rows:
        x = row["x"]
        before = x.get("上回合状态") or {}
        delta = (x.get("本回合变化") or {}).get("变化") or {}
        viewpoint = viewpoint_name(x.get("视角"))
        person = (before.get("人物") or {}).get(viewpoint) or {}
        location = person.get("位置")
        scene = {
            "viewpoint": viewpoint,
            "location": location,
            "locationLines": [place_line(before, location)] if location else [],
            "present": present_names(before, location),
        }
        for name, ops in delta.items():
            if name not in (before.get("人物") or {}):
                continue
            if "位置" in ops:
                origin = (before["人物"][name] or {}).get("位置")
                if origin and origin != ops["位置"]:
                    fact = {"kind": "moved", "name": name, "from": origin, "to": ops["位置"]}
                    fact["phrase"] = fact_phrase(fact)
                    beats.append(_beat(f"lib-{row['id']}-move-{name}", "library", row["id"],
                                       split_of.get(row["id"], "train"), scene, fact))
            for goal in ops.get("完成任务") or []:
                fact = {"kind": "task_achieved", "name": name, "goal": goal}
                fact["phrase"] = fact_phrase(fact)
                beats.append(_beat(f"lib-{row['id']}-task-{len(beats)}", "library", row["id"],
                                   split_of.get(row["id"], "train"), scene, fact))
            for text in ops.get("新增个性") or []:
                fact = {"kind": "personality_changed", "name": name, "text": text}
                fact["phrase"] = fact_phrase(fact)
                beats.append(_beat(f"lib-{row['id']}-trait-{len(beats)}", "library", row["id"],
                                   split_of.get(row["id"], "train"), scene, fact))
            if "精神值" in ops:
                fact = {"kind": "sanity_changed", "name": name,
                        "from": (before["人物"][name] or {}).get("精神值"), "to": ops["精神值"]}
                fact["phrase"] = fact_phrase(fact)
                beats.append(_beat(f"lib-{row['id']}-sanity-{name}", "library", row["id"],
                                   split_of.get(row["id"], "train"), scene, fact))
    return beats


def _beat(beat_id: str, source: str, source_id: str, split: str,
          scene: Dict[str, Any], fact: Dict[str, Any],
          time: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": beat_id,
        "source": source,
        "sourceId": source_id,
        "split": split,
        "scene": scene,
        "fact": fact,
        "time": time,
        "prompt": beat_prompt(scene, fact, time),
        "promptLiteral": beat_prompt(scene, fact, time, literal=True),
    }


# --------------------------------------------------------------- world beats

# Locations held out of training so acceptance can check unseen rooms.
HELD_OUT_LOCATIONS = {"tower", "bell_room", "top", "control"}

# A compact, hand-checked personality-change text set for the product world.
TRAITS = [
    "决定不再替别人做决定", "开始把护目镜当成自己的东西", "愿意在交火里先开口",
    "不再追问诺诺为什么留下", "对芬格尔的玩笑不再接话", "肯把后背交给刚认识的人",
    "学会先看地上的弹壳再迈步", "把输赢看得比同伴轻", "愿意承认自己害怕",
    "开始留意别人手上的伤", "不再假装听不见枪声", "决定这次不躲",
]


def world_beats(world: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    characters = world["characters"]
    locations = world["initial"]["locations"]
    names = world["initial"]["characters"]
    by_name = {entry["name"]: key for key, entry in names.items()}
    loc_children: Dict[str, List[str]] = {}
    for key, entry in locations.items():
        parent = entry.get("parentLocationId")
        if parent:
            loc_children.setdefault(parent, []).append(key)
    beats: List[Dict[str, Any]] = []
    for index, (char_id, character) in enumerate(characters.items()):
        name = names[char_id]["name"]
        here = character["position"]["containerId"]
        here_name = locations[here]["name"]
        siblings = loc_children.get(here, [])
        parents = [locations[here]["parentLocationId"]] if locations[here].get("parentLocationId") else []
        destinations = [key for key in siblings + parents if key != here
                        and key not in HELD_OUT_LOCATIONS][:3]
        for target in destinations[:2]:
            scene = _world_scene(world, char_id, here, [name])
            fact = {"kind": "moved", "name": name, "from": here_name,
                    "to": locations[target]["name"]}
            fact["phrase"] = fact_phrase(fact)
            beats.append(_beat(f"world-{char_id}-move-{target}", "world", char_id,
                               "train", scene, fact))
        tasks = [task for task in character["tasks"].values() if task["status"] == "pending"]
        for task in tasks[:2]:
            scene = _world_scene(world, char_id, here, [name])
            fact = {"kind": "task_achieved", "name": name, "goal": task["goal"]}
            fact["phrase"] = fact_phrase(fact)
            beats.append(_beat(f"world-{char_id}-task-{task['id']}", "world", task["id"],
                               "train", scene, fact))
        trait = TRAITS[index % len(TRAITS)]
        scene = _world_scene(world, char_id, here, [name])
        fact = {"kind": "personality_changed", "name": name, "text": trait}
        fact["phrase"] = fact_phrase(fact)
        beats.append(_beat(f"world-{char_id}-trait", "world", char_id, "train", scene, fact))
        sanity = character.get("sanity", 50)
        delta = 5 if sanity >= 50 else -5
        fact = {"kind": "sanity_changed", "name": name, "from": sanity, "to": sanity + delta}
        fact["phrase"] = fact_phrase(fact)
        beats.append(_beat(f"world-{char_id}-sanity", "world", char_id, "train", scene, fact))
    # Time beats: the page's delta may be time-only.
    for index, (amount, unit) in enumerate([(1, "minute"), (2, "minute"), (3, "minute"),
                                            (5, "minute"), (10, "minute"), (15, "minute"),
                                            (1, "hour")]):
        char_id = list(characters)[index % len(characters)]
        name = names[char_id]["name"]
        here = characters[char_id]["position"]["containerId"]
        scene = _world_scene(world, char_id, here, [name])
        fact = {"kind": "time", "name": name, "phrase": "这一拍只有时间过去，没有别的事情发生"}
        beats.append(_beat(f"world-time-{amount}-{unit}", "world", "time", "train", scene, fact,
                           {"amount": amount, "unit": unit}))
    return beats


def _world_scene(world: Dict[str, Any], char_id: str, location_id: str,
                 extra: List[str]) -> Dict[str, Any]:
    characters = world["characters"]
    locations = world["initial"]["locations"]
    location = locations[location_id]
    view = world["initial"]["characters"][char_id]
    present = [view["name"]]
    for other_id, other in characters.items():
        if other_id == char_id:
            continue
        if other["position"]["containerId"] == location_id:
            present.append(world["initial"]["characters"][other_id]["name"])
    for name in extra:
        if name not in present:
            present.append(name)
    return {
        "viewpoint": view["name"],
        "location": location["name"],
        "locationLines": [f"{location['name']}：{clip(location.get('initialAppearance'))}"],
        "present": present,
    }


def main() -> int:
    rows = load_rows()
    split = load_split()
    beats = library_beats(rows, split)
    world = load_world()
    beats.extend(world_beats(world, rows))
    seen = set()
    unique = []
    for beat in beats:
        key = beat["prompt"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(beat)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        for beat in unique:
            handle.write(json.dumps(beat, ensure_ascii=False) + "\n")
    counts: Dict[str, int] = {}
    for beat in unique:
        key = f"{beat['source']}/{beat['fact']['kind']}"
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"beats": len(unique), "counts": counts,
                      "splits": {name: sum(1 for b in unique if b["split"] == name)
                                 for name in ("train", "dev", "test")}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
