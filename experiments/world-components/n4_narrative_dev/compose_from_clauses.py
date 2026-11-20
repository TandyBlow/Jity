# Assemble verbalizer clauses into a scene paragraph (deterministic, no model).
#
# Takes one clause per fact (from the verbalizer reports), orders clauses by
# the N3 group order, joins them, and checks that every fact is still
# covered and no actor swap was introduced by the join.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/compose_from_clauses.py

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))

import n2_perspective as n2  # noqa: E402
import n3_organize as n3  # noqa: E402

REPORTS = [
    HERE / "verbalizer-rerank-report.json",
    HERE / "verbalizer-report.json",
]


# Production gap: pronouns must come from character data, not this table.
PRONOUN = {"char_shen": "他", "char_gu": "他", "char_han": "他",
           "char_ye": "她", "char_atang": "她", "char_qi": "她",
           "char_lu": "他", "char_aluo": "她", "char_shi": "他"}
NAME_TO_PRONOUN = {}


def dedupe_subjects(pieces):
    """Replace a repeated leading subject with a pronoun after the first
    mention; the fact's actor is unchanged, only the surface form."""
    out, last = [], None
    for piece in pieces:
        head = piece[:3]
        name = next((n for n in NAME_TO_PRONOUN if piece.startswith(n)), None)
        if name and name == last:
            pron = NAME_TO_PRONOUN[name]
            piece = pron + piece[len(name):]
        elif name:
            last = name
        out.append(piece)
    return out


def load_clauses():
    clauses = {}
    for p in REPORTS:
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for split in ("newWorld", "dev", "train"):
            for s in d.get("samples", {}).get(split, []):
                pid = s["pairId"]
                if pid not in clauses:
                    clauses[pid] = s["output"]
    return clauses


def main():
    world = json.loads((HERE / "holdout_world.json").read_text(encoding="utf-8"))
    names = {cid: ch["name"] for cid, ch in world["characters"].items()}
    clauses = load_clauses()
    NAME_TO_PRONOUN.clear()
    NAME_TO_PRONOUN.update({ch["name"]: PRONOUN[cid]
                            for cid, ch in world["characters"].items()
                            if cid in PRONOUN})
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
        order += [f["factId"] for f in selected
                  if f["factId"] not in order]
        by_id = {f["factId"]: f for f in selected}
        pieces, missing = [], []
        for fid in order:
            f = by_id[fid]
            if f["kind"] == "time":
                continue
            pid = f"vbh:{case['id']}:{fid}"
            if pid not in clauses:
                missing.append(fid)
                continue
            pieces.append(clauses[pid])
        pieces = dedupe_subjects(pieces)
        paragraph = "".join(pieces)
        # re-check binding from the joined text
        problems = []
        for fid in order:
            f = by_id[fid]
            if f["kind"] in ("time", "no_change"):
                continue
            if f["name"] not in paragraph:
                problems.append(f"lost-subject:{fid}:{f['name']}")
        present_names = {names.get(e, e) for e in case["sceneState"]["present"]}
        for other in names.values():
            if other not in present_names and other in paragraph:
                problems.append(f"extra-person:{other}")
        results.append({
            "id": case["id"], "clauses": pieces, "missing": missing,
            "paragraph": paragraph, "problems": problems,
            "chars": len(paragraph),
        })
        print(case["id"], "clauses", len(pieces), "missing", missing,
              "problems", problems, flush=True)
        print("  ", paragraph, flush=True)

    ok = [r for r in results if not r["problems"] and not r["missing"]]
    report = {
        "purpose": "deterministic clause composition from verbalizer output",
        "rows": len(results),
        "clean": len(ok),
        "meanChars": round(sum(r["chars"] for r in results) / len(results), 1),
        "results": results,
    }
    pathlib.Path(HERE / "compose-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8")
    print("clean", len(ok), "/", len(results),
          "mean chars", report["meanChars"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
