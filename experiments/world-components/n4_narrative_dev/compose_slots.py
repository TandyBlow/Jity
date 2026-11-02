# Comparison arm: slot-selected, surface-constrained scene sentences.
#
# This is a baseline arm, not the product. It selects 1-2 phenomena from the
# location's own feature inventory and realizes them from a small hand-written
# surface bank keyed by phenomenon + weather class + light. No model call.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/compose_slots.py

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(HERE))

import n2_perspective as n2  # noqa: E402
import n3_organize as n3  # noqa: E402
from compose_full import (PRONOUN, TARGET_MAX, TARGET_MIN, grams,  # noqa: E402
                          load_report, repeated_inside)
from scene_check import check as scene_check  # noqa: E402

# phenomenon -> surface forms, conditioned only on what the scene data says
SURFACE = {
    # 云关驿
    "屋檐冰凌": ["屋檐挂着一排冰凌，雪水顺着檐口往下滴。",
                 "檐口的冰凌很厚，风一过就发出细响。"],
    "木门": ["木门上结着一层霜，推手的地方已经磨亮。",
             "木门缝里透出炭火的暖光。"],
    "炭火": ["炭盆里的火压得很低，映得墙上发红。",
             "炭火的气味在大堂里散不开。"],
    "石阶": ["石阶上落着雪，踩过的地方留下水印。",
             "石阶被雪水打湿，边角结着薄冰。"],
    # 风口岭
    "石道": ["石道被雪埋了一半，只露出几块灰石。",
             "石道上的雪被风推成一道一道的棱。"],
    "雪粒": ["雪粒被横风吹成一片白线。",
             "雪粒打在石头上，声音又密又轻。"],
    "石堆": ["石堆上压着雪，边角露出经幡的绳头。",
             "石堆被雪盖住，只剩一个模糊的轮廓。"],
    "经幡": ["经幡被风吹得笔直，布角啪啪作响。",
             "经幡在风里翻卷，绳结上挂着冰碴。"],
    "旧马棚": ["旧马棚的门板歪着，里面堆着干草。",
               "马棚里黑得很快，干草的气味很重。"],
    # 雪溪
    "石桥": ["石桥的栏上结着薄冰，桥下的水声很轻。",
             "石桥面积着雪，中间被踩出一条湿痕。"],
    "冰面": ["溪面结着薄冰，底下还有一线黑水。",
             "冰面反着灰白的光，边上有碎冰。"],
    "枯草": ["岸边的枯草被雪压弯，露出几根硬茎。",
             "枯草从雪里支出来，被风吹得发抖。"],
    "溪水": ["溪水在冰缝里流，声音断断续续。",
             "水边的雪被浸得发灰。"],
    # 望雪台
    "石台": ["石台被雪盖住，只有台沿露出石色。",
             "石台面上结着冰，脚踩上去发滑。"],
    "木梯": ["木梯上落着雪，横档被踩得发亮。",
             "木梯的绳子冻硬了，风一吹就贴在柱子上。"],
    "铜铃架": ["铜铃架在风里轻响，铃身上挂着霜。",
               "铜铃架的木头冻裂了一道口子。"],
    "铃绳": ["铃绳被风吹得乱甩，打在柱子上。",
             "铃绳冻得发硬，垂在台边。"],
}
# weather-only slots, used when a second sentence is needed
WEATHER_SURFACE = {
    "雪": ["雪一直没有停，风把雪吹得斜着落。",
           "雪压在石头上，边角落出一层白。"],
    "风": ["风从山口灌下来，带着雪沫。",
           "风很硬，吹得衣角发紧。"],
    "雾": ["雾贴着地面走，远处的石头看不清。",
           "雾里只看得见脚下几步。"],
    "雨": ["雨点打在木头和石头上，声音很密。",
           "雨丝斜着落进来，地上很快湿了。"],
}


def weather_key(scene):
    for k in ("雪", "雾", "雨", "风"):
        if k in scene:
            return k
    return "风"


def phenomena(world, root_id):
    loc = world["locations"][root_id]
    props = list(loc.get("features", []))
    out = [p for p in props if p in SURFACE]
    return out or list(SURFACE)[:2]


def pick(case, world):
    sc = case["sceneState"]
    root = sc["locationPath"][0]
    pool = phenomena(world, root)
    seed = int(hashlib.sha256(case["id"].encode()).hexdigest(), 16)
    first = pool[seed % len(pool)]
    out = [SURFACE[first][seed % len(SURFACE[first])]]
    if len("".join(out)) < 26:
        wx = WEATHER_SURFACE[weather_key(" ".join([sc["weather"], sc["atmosphere"]]))]
        out.append(wx[seed % len(wx)])
    return out


def build_row(case, world):
    sc = case["sceneState"]
    root = sc["locationPath"][0]
    pov = world["characters"][case["perspective"]["entityId"]]
    body = [
        "地点=" + world["locations"][root]["name"],
        "场景=" + "；".join([sc["time"], sc["weather"], sc["wind"],
                            sc["light"], sc.get("atmosphere", "")]).strip("；"),
        "视角=" + pov["name"],
    ]
    return {"input": chr(10).join(body) + chr(10), "pairId": case["id"]}


def main():
    world = json.loads((HERE / "holdout_world.json").read_text(encoding="utf-8"))
    names = {cid: ch["name"] for cid, ch in world["characters"].items()}
    pronouns = {ch["name"]: PRONOUN[cid] for cid, ch in world["characters"].items()
                if cid in PRONOUN}
    facts_text = load_report("verbalizer-rerank-report.json", "newWorld")
    if not facts_text:
        facts_text = load_report("verbalizer-report.json", "newWorld")
    cases = [json.loads(l) for l in
             (HERE / "holdout_corpus.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip()]

    results = []
    for case in cases:
        facts = [dict(f) for f in case["facts"]]
        for f in facts:
            if f.get("entityId") in world["characters"]:
                f["entityGroup"] = "characters"
        res = n2.classify_facts(facts, case["perspective"], may_policy="select",
                                visible_other_actions=True)
        selected = [f for f in facts if f["factId"] in set(res["selectedFactIds"])]
        plan = n3.plan_v3(selected, names, cross_group_guard=True)
        order = []
        for sent in plan.get("sentences", []):
            order.extend(sent.get("factIds", []))
        order += [f["factId"] for f in selected if f["factId"] not in order]
        by_id = {f["factId"]: f for f in selected}

        clauses, last = [], None
        for fid in order:
            f = by_id[fid]
            if f["kind"] == "time":
                continue
            pid = f"vbh:{case['id']}:{fid}"
            t = facts_text.get(pid)
            if not t:
                continue
            head = next((n for n in pronouns if t.startswith(n)), None)
            if head and head == last:
                t = pronouns[head] + t[len(head):]
            elif head:
                last = head
            clauses.append(t)

        openers = pick(case, world)
        # second opener only when the first is too short and they do not echo
        if len(openers[0]) + sum(len(c) for c in clauses) < TARGET_MIN:
            for cand in pick(case, world):
                if (cand not in openers
                        and len(grams(cand) & grams(openers[0])) < 2):
                    if not repeated_inside(cand):
                        openers.append(cand)
                        break
        paragraph = "".join(openers) + "".join(clauses)
        row = build_row(case, world)
        struct = [scene_check(row, o) for o in openers]
        problems = []
        for fid in order:
            f = by_id[fid]
            if f["kind"] in ("time", "no_change"):
                continue
            if f["name"] not in paragraph and pronouns.get(f["name"], "?") not in paragraph:
                problems.append(f"lost-fact:{fid}")
        present = {names.get(e, e) for e in case["sceneState"]["present"]}
        for n in names.values():
            if n not in present and n in paragraph:
                problems.append(f"extra-person:{n}")
        results.append({
            "id": case["id"], "openers": openers, "paragraph": paragraph,
            "chars": len(paragraph),
            "openerStructOk": all(s["ok"] for s in struct),
            "openerReasons": [s["reasons"] for s in struct if not s["ok"]],
            "factsOk": not problems, "problems": problems,
            "lengthOk": TARGET_MIN <= len(paragraph) <= TARGET_MAX,
        })
        print(("OK " if all([results[-1]["openerStructOk"], results[-1]["factsOk"]])
               else "CHK"), case["id"], len(paragraph), "|", paragraph, flush=True)

    lengths = [r["chars"] for r in results]
    report = {
        "purpose": "slot-selected scene sentences (baseline comparison arm)",
        "rows": len(results),
        "factsOk": sum(1 for r in results if r["factsOk"]),
        "openerStructOk": sum(1 for r in results if r["openerStructOk"]),
        "lengthInTarget": sum(1 for r in results if r["lengthOk"]),
        "chars": {"min": min(lengths), "max": max(lengths),
                  "mean": round(sum(lengths) / len(lengths), 1)},
        "results": results,
    }
    pathlib.Path(HERE / "compose-slots-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8", newline=chr(10))
    print("facts", report["factsOk"], "/", len(results),
          "struct", report["openerStructOk"], "length", report["lengthInTarget"],
          "chars", report["chars"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
