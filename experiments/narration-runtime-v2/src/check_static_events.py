# -*- coding: utf-8 -*-
"""Screen narration for one failure class: static or conditional material that
the model turns into a new current event.

This is an offline screening aid for lane 10, not a product gate and not a
replacement for 01's checker. It exists because `accepted=true` from the
alignment checker only means "no known rule was violated": in lane 02's Qwen3
free-day arms an auto-accepted paragraph gave a static exercise-rule sign a
voice, turned a conditional trait ("听见远处枪声会下意识缩肩") into a current
gunshot, and tilted a pistol that the input says lies muzzle-down.

Five general checks driven by the licensed input text (no test-name branches):

  static_as_speaker    a location/item/described object is followed by
                       发出/传来/响起/说/提醒/喊/提示/低语/回响
  invented_sound       "传来/听见 X 的声音" where X is not a licensed entity
  stance_added         靠墙/倚/蹲下/坐下/站起/站定/站在/半跪 appears only in prose
  handling_added       an item is touched/held/opened/placed with a verb the input
                       does not license
  conditional_as_event a trigger the input states as conditional appears as a
                       present event

Usage:
    python src/check_static_events.py --run-json <file> [--select id]
    python src/check_static_events.py --input-text in.txt --prose out.txt
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from typing import Any, Dict, List, Set

SPEECH_VERBS = ("发出", "传来", "响起", "响了", "说", "提醒", "喊", "提示", "低语", "回响")
STANCE_WORDS = ("靠墙", "靠在墙", "倚着", "倚在", "蹲下", "蹲着", "坐下", "坐着", "站起",
                "站定", "站在", "半跪", "跪着", "趴在", "躺着")
HANDLING_VERBS = ("摸", "抚", "握", "抓", "拿起", "放下", "抬起", "举起", "推开", "打开",
                  "合上", "盖上", "扣动", "拨", "擦", "抱着", "塞进", "插进", "摩挲", "碰")
SENTENCE = re.compile(r"[^。！？\n]+[。！？]?")
SPLIT_CLAUSE = re.compile("[。；;\n]")
NOT_HANDLED = re.compile(r"没有|没|未|不曾|不再")


def read(path: str) -> str:
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def licensed_entities(input_text: str) -> Dict[str, Set[str]]:
    """Names from the input's own 【…】 sections; anything else that acts is suspect."""
    people: Set[str] = set()
    items: Set[str] = set()
    places: Set[str] = set()
    parts = re.split("【(人物|物品|地点|变化|正文|视角)】", input_text)
    section = None
    for index, part in enumerate(parts):
        if index % 2 == 1:
            section = part
            continue
        if section == "人物":
            for name in re.findall(r"([\u4e00-\u9fff]{2,4})：", part):
                people.add(name)
        elif section == "物品":
            for name in re.findall(r"([\u4e00-\u9fff]{2,10})（在", part):
                items.add(name)
        elif section == "地点":
            for name in re.findall(r"([\u4e00-\u9fff]{2,8})（在", part):
                places.add(name)
            for name in re.findall(r"([\u4e00-\u9fff]{2,8})：", part):
                places.add(name)
    return {"people": people, "items": items, "places": places}


def static_names(input_text: str, entities: Dict[str, Set[str]]) -> Set[str]:
    """Static things the prose may describe but must not make act."""
    statics = set(entities["items"]) | set(entities["places"])
    for clause in re.findall(r"([\u4e00-\u9fff]{2,8})(?:牌|图|绳|门|窗|墙|灯|箱|柜|架)", input_text):
        statics.add(clause)
    return {name for name in statics if len(name) >= 2 and name not in entities["people"]}


def sentences(text: str) -> List[str]:
    return [part.strip() for part in SENTENCE.findall(text) if part.strip()]


def conditional_triggers(input_text: str) -> List[str]:
    """'听见远处枪声会下意识缩肩' -> ['枪声']."""
    triggers: List[str] = []
    for clause in SPLIT_CLAUSE.split(input_text):
        if "会" not in clause:
            continue
        matched = re.findall(r"([\u4e00-\u9fff]{2,4})(?:会|就)", clause)
        if matched:
            triggers.append(matched[-1][-2:])
    return [trigger for trigger in triggers if len(trigger) >= 2]


def screen(input_text: str, prose: str) -> Dict[str, Any]:
    entities = licensed_entities(input_text)
    statics = static_names(input_text, entities)
    triggers = conditional_triggers(input_text)
    findings: List[Dict[str, str]] = []

    if statics:
        alternatives = "|".join(sorted(map(re.escape, statics), key=len, reverse=True))
        speaker = re.compile("(" + alternatives + ")[里中上内]?(?:的)?(?:"
                             + "|".join(SPEECH_VERBS) + ")")
    else:
        speaker = None
    sound = re.compile(r"(?:传来|听见|听到)([^，。]{0,10}?)(?:的)?"
                       r"(?:声音|响动|声响|回响|脚步声)")

    for sentence in sentences(prose):
        if speaker is not None:
            hit = speaker.search(sentence)
            # "林川的脚步声在门厅里回响" has 门厅 as a place, not the subject.
            if hit and "的" in sentence[max(0, hit.start() - 4):hit.start()]:
                hit = None
            if hit:
                findings.append({"kind": "static_as_speaker", "entity": hit.group(1),
                                 "sentence": sentence})
        heard = sound.search(sentence)
        if heard:
            source = heard.group(1)
            licensed = (any(name in source for name in entities["people"])
                        or any(name in source for name in entities["items"])
                        or any(name in sentence[:heard.start()] for name in entities["people"]))
            if not licensed:
                findings.append({"kind": "invented_sound", "source": source,
                                 "sentence": sentence})
        stays_put = any(marker in sentence for marker in ("原地", "原处", "原位置", "不动", "没有移动"))
        for word in STANCE_WORDS:
            if word in sentence and word not in input_text and not stays_put:
                findings.append({"kind": "stance_added", "word": word, "sentence": sentence})
                break
        for item in entities["items"]:
            if item not in sentence:
                continue
            at = sentence.find(item)
            window = sentence[max(0, at - 8):at + len(item) + 8]
            if NOT_HANDLED.search(window):
                continue
            used = [verb for verb in HANDLING_VERBS if verb in window]
            licensed_verbs = [verb for verb in used if verb in input_text]
            if used and not licensed_verbs:
                findings.append({"kind": "handling_added", "item": item,
                                 "verb": used[0], "sentence": sentence})
                break
        for trigger in triggers:
            if trigger in sentence and re.search("(传来|响起|响|听到|听见|一声)", sentence):
                findings.append({"kind": "conditional_as_event", "trigger": trigger,
                                 "sentence": sentence})
                break

    seen: Set[tuple] = set()
    unique: List[Dict[str, str]] = []
    for finding in findings:
        key = (finding["kind"],
               finding.get("entity") or finding.get("item") or finding.get("word")
               or finding.get("trigger") or finding.get("source"),
               finding["sentence"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return {"licensed": {"people": sorted(entities["people"]),
                         "items": sorted(entities["items"]),
                         "places": sorted(entities["places"]),
                         "static": sorted(statics)},
            "conditionalTriggers": triggers,
            "findings": unique,
            "clean": not unique,
            "note": "offline screening aid; accepted=true in the product checker does not "
                    "imply these findings are absent"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-json", default="")
    parser.add_argument("--select", default="")
    parser.add_argument("--input-text", default="")
    parser.add_argument("--prose", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    results = []
    if args.run_json:
        with io.open(args.run_json, encoding="utf-8") as handle:
            data = json.load(handle)
        for run in data.get("runs", []):
            if args.select and args.select not in run.get("id", ""):
                continue
            results.append({"id": run["id"], "accepted": run.get("accepted"),
                            **screen(run.get("inputText", ""), run.get("text", ""))})
    else:
        results.append({"id": "manual", **screen(read(args.input_text), read(args.prose))})

    for result in results:
        print("=" * 70)
        print(result["id"], "| accepted in checker:", result.get("accepted"),
              "| clean here:", result["clean"])
        for finding in result["findings"]:
            subject = (finding.get("entity") or finding.get("item") or finding.get("word")
                       or finding.get("trigger") or finding.get("source"))
            print(f"  - {finding['kind']}: {subject}")
            print(f"    {finding['sentence'][:90]}")
    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"runs": results}, ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
