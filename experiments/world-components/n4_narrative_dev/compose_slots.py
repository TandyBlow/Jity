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

import scene_bank  # noqa: E402

SURFACE = scene_bank.SURFACE
WEATHER_SURFACE = scene_bank.WEATHER


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


_ASSIGN = {}


def pick(case, world, index):
    """Round-robin over the location's own phenomena so that the 12 cases do
    not reuse the same sentence; the index is the case ordinal, not a hash,
    so assignments are stable and inspectable."""
    sc = case["sceneState"]
    root = sc["locationPath"][0]
    pool = phenomena(world, root)
    out = []
    for k, name in enumerate(pool):
        variants = SURFACE[name]
        out.append(variants[(index + k) % len(variants)])
    return pool, out


def choose_openers(case, world, index, clauses):
    """Take up to three sentences: first a location phenomenon, then weather
    lines, stopping once the paragraph reaches the lower bound."""
    pool, loc_variants = pick(case, world, index)
    weather_key_ = weather_key(" ".join([case["sceneState"]["weather"],
                                         case["sceneState"].get("atmosphere", "")]))
    wx = WEATHER_SURFACE[weather_key_]
    order = [loc_variants[index % len(loc_variants)]] + [
        loc_variants[(index + 2) % len(loc_variants)],
        wx[index % len(wx)],
        loc_variants[(index + 4) % len(loc_variants)],
    ]
    chosen, used, total = [], set(), sum(len(c) for c in clauses)
    for cand in order:
        if len(chosen) >= 3:
            break
        if cand in chosen or repeated_inside(cand):
            continue
        if chosen and len(grams(cand) & used) >= 2:
            continue
        chosen.append(cand)
        used |= grams(cand)
        total += len(cand)
        if total >= TARGET_MIN:
            break
    return chosen


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

        openers = choose_openers(case, world, len(results), clauses)
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
