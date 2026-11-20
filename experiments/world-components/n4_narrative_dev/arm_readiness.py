"""What exists for the three task shapes, counted from the files on disk.

No modelling, no judging: this only answers "can the three arms be trained on
the same source split yet".
"""
import json, pathlib
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "artifacts" / "world-components" / "n4-arm-readiness-r1.json"


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8")
            .splitlines() if l.strip()]


def main():
    formal = rows(HERE / "formal_pairs.jsonl")
    verb = rows(HERE / "verbalizer_pairs.jsonl")
    c140 = rows(HERE.parent / "n4_rewrite60" / "corpus140.jsonl")

    fsplit = {r["sourceId"]: r["split"] for r in formal}
    per_source = Counter(r["sourceId"] for r in verb)
    facts_by_split = Counter(fsplit.get(r["sourceId"], "unknown") for r in verb)
    uncovered = [s for s in fsplit if s not in per_source]

    rec = {
        "purpose": "three-arm data readiness, counted from disk",
        "paragraph": {
            "n4n": {"file": "formal_pairs.jsonl", "rows": len(formal),
                    "bySplit": dict(Counter(r["split"] for r in formal))},
            "corpus140": {"file": "../n4_rewrite60/corpus140.jsonl",
                          "rows": len(c140),
                          "bySplit": dict(Counter(r["split"] for r in c140)),
                          "note": "old dev/test contaminated: 18 rows moved to train; "
                                  "cannot serve as unseen test"},
        },
        "fact": {
            "n4n": {"file": "verbalizer_pairs.jsonl", "rows": len(verb),
                    "sourcesCovered": len(per_source),
                    "factsPerSource": dict(Counter(per_source.values())),
                    "byInheritedSplit": dict(facts_by_split),
                    "sourcesWithoutFactTarget": uncovered,
                    "note": "file labels every row 'vb-train'; splits must be "
                            "inherited from the source split, not from the file"},
            "corpus140": {"rows": 0, "note": "no per-fact targets exist for corpus140"},
        },
        "group": {
            "n4n": {"rows": 0, "note": "no N3 plan or group-level target for n4n rows"},
            "corpus140": {"rows": 0,
                          "note": "corpus140 rows carry facts but no plan/group targets"},
            "elsewhere": {"n4_corpus_v2": "grouped targets exist for the A/B/C "
                                          "families, which are a different source "
                                          "family and not comparable to n4n"},
        },
        "verdict": {},
    }
    p_ok = bool(rec["paragraph"]["n4n"]["rows"])
    f_ok = (len(per_source) == len(fsplit)) and not uncovered
    g_ok = bool(rec["group"]["n4n"]["rows"])
    rec["verdict"] = {
        "sharedSourceFamily": "n4n (120 sources)",
        "paragraphReady": p_ok,
        "factReady": f_ok,
        "groupReady": g_ok,
        "threeArmsComparable": p_ok and f_ok and g_ok,
        "blocker": None if g_ok else
        "group targets need factId-level alignment; punctuation splitting is not "
        "accepted as alignment",
    }
    ex = ROOT / "artifacts" / "world-components" / "n4-run-exclusions-r1.json"
    ex.write_text(json.dumps({
        "purpose": "rows excluded from length audit / training material",
        "excluded": [{"id": "n4n-03",
                      "file": "n4_rewrite60/corpus140.jsonl",
                      "reason": "moved fact names from=河心, which is absent from "
                                "world.json; it is a data gap, not a judge result",
                      "decision": "excluded from arm material and from judge rates; "
                                  "keep the row on disk unchanged so the gap stays visible",
                      "alternativeNotTaken": "add 河心 to world.json; rejected because "
                                             "it would change the frozen entity tables"}],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rec["verdict"], ensure_ascii=False, indent=1))
    print("fact by split:", dict(facts_by_split))
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
