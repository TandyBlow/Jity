# -*- coding: utf-8 -*-
"""Turn the frozen free-day-root fixture into the review dataset shape.

The fixture (results/quality/free-day-root-scenario.json) is a read-only
product snapshot: scene notes, present people, inventory, and committed facts
(at/sanity for the whole roster). This script restates it as
{视角/上回合状态/本回合变化/本回合状态} so the same narration can be reviewed
with the same checker as the authored corpus. No new state is invented: people
not in the scene only get their committed position and sanity.
"""
import json
import sys

FIXTURE = "../../../results/quality/free-day-root-scenario.json"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else FIXTURE
    out = sys.argv[2] if len(sys.argv) > 2 else None
    fixture = json.loads(open(path, encoding="utf-8").read())
    scene = fixture["scene"]
    policy = fixture["policy"]
    facts = fixture["committed"]["facts"]
    at = {f["name"]: f["location"] for f in facts if f["kind"] == "at"}
    sanity = {f["name"]: f["value"] for f in facts if f["kind"] == "sanity"}

    places = {}
    for name in policy["locations"]:
        places[name] = {"位于": None, "外貌": []}
    for name in [scene["location"], *(p["location"] for p in policy["knownPositions"])]:
        places.setdefault(name, {"位于": None, "外貌": []})
    for name in places:
        if name != scene["location"] and "，".join(places[name]["外貌"]):
            continue
    places[scene["location"]]["外貌"] = scene["placeNotes"]

    people = {}
    for name in policy["roster"]:
        people[name] = {
            "位置": at.get(name) or next((k["location"] for k in policy["knownPositions"] if k["name"] == name), None),
            "精神值": sanity.get(name),
            "外貌": [],
            "个性": [],
            "任务": {"大任务": None, "小任务": []},
        }
    for person in scene["present"]:
        entry = people[person["name"]]
        for line in person["note"].split("。"):
            if not line:
                continue
            entry["外貌"].append(line.strip())
    items = {}
    for item in scene.get("objects") or []:
        items[item["name"]] = {"位置": scene["location"], "外貌": [item["note"]]}
    for item in scene.get("inventory") or []:
        owner = next((name for name in people if item["name"].startswith(f"{name}的")), None)
        items[item["name"]] = {"位置": owner or scene["location"], "外貌": [item["note"]]}

    dataset = {
        "视角": f"主角视角（{fixture['viewpoint']['name']}）",
        "上回合状态": {"地点": places, "人物": people, "物品": items},
        "本回合变化": {"变化": {}},
        "本回合状态": {"人物": {}, "物品": {}},
    }
    text = json.dumps(dataset, ensure_ascii=False, indent=1)
    if out:
        open(out, "w", encoding="utf-8", newline="\n").write(text)
        print(f"wrote {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
