"""Build the blind packet and calibration set for the independent reviewer.

Fixes from the 2026-11-09 review:
- the packet now carries the full scene, the character identities with their
  entityIds and authoritative traits, and the visible items, so the reviewer can
  judge whether a description is authorised and can tell two same-name actors
  apart; the old N6/D4 labels stay hidden;
- the calibration key separates invented PROPER NAMES from invented EVENTS (the
  previous text claimed three names while only 王五 and 柳溪渡 are names, and
  c3's 钟声 was neither labelled nor excluded).

Usage: python -X utf8 make_reviewer_packet.py
"""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUN = HERE / "out" / "real-batch-v3.json"
CASES = HERE / "fixtures" / "batch-v1-cases.json"
PACKET = HERE / "fixtures" / "reviewer-packet-v3.json"
CALIB = HERE / "fixtures" / "reviewer-calibration.json"
KEY = HERE / "fixtures" / "reviewer-calibration-key.json"

TRAITS = ("initialPersonality", "initialAppearance")


def parse_scene(render_text):
    lines = render_text.split(chr(10))
    scene = {"location": None, "appearance": None, "visible": [],
             "characterRows": []}
    for line in lines:
        if line.startswith("地点="):
            scene["location"] = line.split("=", 1)[1]
        elif line.startswith("地点外貌="):
            scene["appearance"] = line.split("=", 1)[1]
        elif line.startswith("同栋="):
            scene["sameBuilding"] = line.split("=", 1)[1]
        elif "｜性格=" in line:
            scene["characterRows"].append(line)
        elif line and "=" in line and "｜" not in line \
                and not line.startswith(("f", "G", "视角", "要求", "正文", "场景",
                                         "人物", "可见", "叙事")):
            name, _, app = line.partition("=")
            scene["visible"].append({"name": name, "appearance": app})
    return scene


def character_state(case):
    state = case["point"]["state"]
    out = []
    for eid, ch in (state.get("characters") or {}).items():
        init = (state.get("initial", {}).get("characters") or {}).get(eid, {})
        changes = ch.get("personalityChanges") or []
        pers = changes[-1]["text"] if changes and changes[-1].get("text") \
            else init.get("initialPersonality")
        achanges = ch.get("appearanceChanges") or []
        app = achanges[-1]["text"] if achanges and achanges[-1].get("text") \
            else init.get("initialAppearance")
        out.append({"entityId": eid, "name": init.get("name"),
                    "personality": pers, "appearance": app})
    return out


def main() -> int:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    cases_doc = json.loads(CASES.read_text(encoding="utf-8"))
    by_id = {c["caseId"]: c for c in cases_doc["cases"]}

    cases = []
    for c in run["cases"]:
        rt = c["renderText"]
        facts = [l for l in rt.split(chr(10)) if l[:1] == "f" and "｜" in l]
        persp = [l for l in rt.split(chr(10)) if l.startswith("视角：")]
        req = [l for l in rt.split(chr(10)) if l.startswith("要求：")]
        scene = parse_scene(rt)
        scene["characters"] = character_state(by_id[c["caseId"]])
        persp_cfg = by_id[c["caseId"]].get("perspective") or {}
        eid = persp_cfg.get("entityId")
        if eid is None and persp_cfg.get("type") == "protagonist":
            eid = (by_id[c["caseId"]]["point"]["state"] or {}).get(
                "protagonistId")
        scene["perspectiveEntityId"] = eid
        cases.append({
            "caseId": c["caseId"],
            "authoritativeFacts": facts,
            "perspective": persp[0] if persp else None,
            "writingRules": req[0] if req else None,
            "scene": scene,
            "text": c["attempts"][0]["output"],
            "finishReason": c["attempts"][0]["finishReason"],
        })

    packet = {
        "version": "reviewer-packet-v3-r2",
        "instructions": [
            "Read the scene, the characters (with entityId and authoritative "
            "traits), the visible items, the facts, the perspective and the "
            "rules, then the text.",
            "For each fact say whether the text conveys it (yes / no / "
            "undetermined) and quote the evidence.",
            "Say whether two same-name actors are confused, whether the text "
            "adds a proper name or an EVENT that is not authorised, and whether "
            "the point of view changes. Keep names and events separate.",
            "Rate readability 1-5. Do not score style preferences.",
            "Label the calibration texts too, without looking for a key.",
        ],
        "labelSchema": {
            "facts": [{"factId": "f0", "conveyed": "yes|no|undetermined",
                       "evidence": "verbatim quote"}],
            "sameNameConfused": "yes|no|undetermined",
            "inventedProperNames": ["verbatim quote"],
            "inventedEvents": ["verbatim quote"],
            "povChanged": "yes|no|undetermined",
            "readability": "1-5",
        },
        "cases": cases,
    }
    PACKET.write_text(json.dumps(packet, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8", newline="\n")

    authority_good = {
        "scene": {"location": "钟楼", "appearance": "旧"},
        "characters": [{"entityId": "char_pa", "name": "管线甲",
                        "personality": "沉稳", "appearance": "常态"}],
        "visible": [],
        "perspectiveEntityId": "char_pa",
        "allowedFacts": ["管线甲从管线镇来到钟楼", "管线甲把铜铃挂回钟楼"],
        "allowedAdditions": ["与场景一致的环境描写", "视角人物的感受"],
    }
    calib = {"version": "reviewer-calibration-r3",
             "note": "every text comes with the authoritative scene, the "
                     "characters (entityId) and the allowed facts, so a label "
                     "can be checked against evidence instead of guessed",
             "texts": [
                 {"id": "c1", "authority": authority_good,
                  "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼。他靠着栏杆喘了口气。"},
                 {"id": "c2", "authority": authority_good,
                  "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼。王五在楼梯口等他。"},
                 {"id": "c3", "authority": authority_good,
                  "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼。钟声在雾里散开。"},
                 {"id": "c4", "authority": authority_good,
                  "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼，又去了柳溪渡。"},
                 {"id": "c5", "authority": authority_good,
                  "text": "管线甲从管线镇来到了钟楼。管线甲并未把铜铃挂回钟楼。"},
                 {"id": "c6", "authority": authority_good,
                  "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼。他的手指还在抖。"},
             ]}

    key = {
        "inventedProperNames": {
            "c2": ["王五"],
            "c4": ["柳溪渡"],
        },
        "inventedEvents": {
            "c2": ["王五在楼梯口等他（新增人物带来新增事件）"],
            "c3": ["钟声在雾里散开（世界状态里没有钟声事件）"],
            "c4": ["又去了柳溪渡（新增移动事件）"],
        },
        "factConveyed": {
            "c1": True, "c2": True, "c3": True, "c4": True,
            "c5": False, "c6": True,
        },
        "notes": {
            "c5": "the result is negated, so the fact is NOT conveyed",
            "c4": "柳溪渡 is a place name that is not in the world; the trip "
                  "there is a separate added event",
            "c3": "the bell sound is an added event, not a proper name",
            "c1": "the deep breath is an allowed feeling, not an event",
            "c6": "the trembling fingers are an allowed feeling, not an event",
        },
    }

    CALIB.write_text(json.dumps(calib, ensure_ascii=False,
                            indent=1) + chr(10),
                            encoding="utf-8",
                            newline=chr(10))
    KEY.write_text(json.dumps(key, ensure_ascii=False,
                          indent=1) + chr(10),
                          encoding="utf-8",
                          newline=chr(10))
    names = sum(len(v) for v in key["inventedProperNames"].values())
    events = sum(len(v) for v in key["inventedEvents"].values())
    print(f"packet: {len(cases)} cases with scene/characters/entityIds -> "
          f"{PACKET.name}")
    print(f"calibration: 6 texts, {names} invented proper names, "
          f"{events} invented events -> {CALIB.name} (key: {KEY.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
