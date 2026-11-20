# Compose the full paragraph: scene sentence + fact clauses (deterministic).
#
# Inputs are the two component reports (scene rerank, verbalizer rerank).
# Nothing is generated here; this only orders and joins, then re-checks the
# facts. Run: python -X utf8 experiments/world-components/n4_narrative_dev/compose_full.py

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))

import n2_perspective as n2  # noqa: E402
import n3_organize as n3  # noqa: E402

PRONOUN = {"char_shen": "他", "char_gu": "他", "char_han": "他",
           "char_ye": "她", "char_atang": "她", "char_qi": "她",
           "char_lu": "他", "char_aluo": "她", "char_shi": "他"}
NUM = re.compile(r"[0-9０-９]+(分钟|小时|秒|点|刻|步)")
TARGET_MIN, TARGET_MAX = 55, 95


def load_report(name, split):
    p = HERE / name
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {s["pairId"]: s["output"] for s in d["samples"].get(split, [])}


def load_scene_candidates():
    p = HERE / "scene-rerank-report.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for s in d["samples"].get("newWorld", []):
        ok = [c["text"] for c in s.get("candidates", []) if c["ok"]]
        if not ok:
            ok = [s["output"]]
        seen, uniq = set(), []
        for t in ok:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        out[s["pairId"]] = uniq
    return out


def grams(text, n=4):
    return {text[i:i + n] for i in range(max(0, len(text) - n + 1))}


def repeated_inside(text):
    """Reject stutter such as 木门把木门: any 2-gram used twice."""
    gs = [text[i:i + 2] for i in range(max(0, len(text) - 1))]
    return any(gs.count(g) >= 2 for g in set(gs))


def pick_openers(cands, need):
    """Choose up to two scene sentences: no internal stutter, no shared
    4-grams with the previous one."""
    chosen, used = [], set()
    for t in cands:
        if len(chosen) >= 3:
            break
        if repeated_inside(t):
            continue
        g = grams(t)
        if len(g & used) >= 2:
            continue
        chosen.append(t)
        used |= g
        if sum(len(c) for c in chosen) >= need:
            break
    return chosen


def main():
    world = json.loads((HERE / "holdout_world.json").read_text(encoding="utf-8"))
    names = {cid: ch["name"] for cid, ch in world["characters"].items()}
    pronouns = {ch["name"]: PRONOUN[cid] for cid, ch in world["characters"].items()
                if cid in PRONOUN}
    scene_cands = load_scene_candidates()
    scene = load_report("scene-rerank-report.json", "newWorld")
    if not scene:
        scene = load_report("scene-report.json", "newWorld")
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
        selected = [f for f in facts
                    if f["factId"] in set(res["selectedFactIds"])]
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
            if pid not in facts_text:
                clauses.append({"factId": fid, "missing": True, "text": ""})
                continue
            t = facts_text[pid]
            head = next((n for n in pronouns if t.startswith(n)), None)
            if head and head == last:
                t = pronouns[head] + t[len(head):]
            elif head:
                last = head
            clauses.append({"factId": fid, "missing": False, "text": t})

        base_clauses = [c["text"] for c in clauses if c["text"]]
        need = max(0, TARGET_MIN - sum(len(x) for x in base_clauses))
        cands = scene_cands.get(f"sch:{case['id']}", [])
        if not cands:
            single = scene.get(f"sch:{case['id']}", "")
            cands = [single] if single else []
        openers = pick_openers(cands, need)
        opener = "".join(openers)
        pieces = openers + base_clauses
        paragraph = "".join(pieces)

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
        if NUM.search(paragraph):
            problems.append("has-duration")
        length_ok = TARGET_MIN <= len(paragraph) <= TARGET_MAX
        stutter = repeated_inside(opener) if opener else False

        results.append({
            "id": case["id"], "opener": opener, "paragraph": paragraph,
            "chars": len(paragraph), "problems": problems,
            "lengthOk": length_ok, "stutter": stutter,
            "missingFacts": [c["factId"] for c in clauses if c["missing"]],
        })
        flag = "OK " if not problems else "CHK"
        print(flag, case["id"], len(paragraph), "|", paragraph, flush=True)

    clean = [r for r in results if not r["problems"]]
    lengths = [r["chars"] for r in results]
    integrity = [r for r in results if not r["problems"]]
    report = {
        "purpose": "full paragraph = scene sentence + fact clauses (no model)",
        "rows": len(results),
        "factIntegrity": len(integrity),
        "stutterRows": sum(1 for r in results if r["stutter"]),
        "chars": {"min": min(lengths), "max": max(lengths),
                  "mean": round(sum(lengths) / len(lengths), 1),
                  "inTarget": sum(1 for x in lengths
                                  if TARGET_MIN <= x <= TARGET_MAX)},
        "results": results,
    }
    pathlib.Path(HERE / "compose-full-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8", newline=chr(10))
    print("fact-integrity", len(integrity), "/", len(results),
          "stutter", report["stutterRows"], "chars", report["chars"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
