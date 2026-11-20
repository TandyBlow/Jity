# N2 perspective-rule acceptance run (commit 1). Runs the PIPELINE
# selection rule (n2_perspective.classify_facts) over the frozen D2 dev set
# (16 items / 92 facts, v3 labels loaded through the frozen guards in
# recompute_must_v3) and compares it against the labelled select-all
# baseline on the same items.
#
# Gates, pre-registered HERE before this run and unchanged since (they
# mirror the C task brief's acceptance line for N2):
#   - selected facts per item > 0 (an empty selection is a failure, not a
#     polite zero)
#   - PER-ITEM must recall >= 0.95 under the default select policy
#   - invalid/unknown fact ids == 0
# Reported, not gated: must precision, may selection rate, invisible
# grounds breakdown, refusal and stop rates — a rule that refused
# everything would pass the recall gate vacuously, so the counts are on
# the record.
#
# Scope notes, recorded rather than hidden:
#   - the D2 dev set is a DEVELOPMENT set (it calibrated the rubric); the
#     numbers here are dev-set gates, not independent-holdout claims;
#   - the items carry no subject task list, so the tracked-task must rule
#     cannot fire here (subject_tasks=None); it is covered by pipeline
#     unit tests (narration_pipeline S12/S14) instead;
#   - this run trains nothing and calls no model.

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "n2_selection"))
import n2_perspective  # noqa: E402
from recompute_must_v3 import FROZEN, LABELS, load_frozen, read_jsonl  # noqa: E402

REPO = HERE.parent.parent
ITEMS = HERE / "n2_selection" / "items.jsonl"
OUT = REPO / "artifacts" / "world-components" / "n2-perspective-rule-r1.json"

MUST_RECALL_GATE = 0.95


def arm_rows(items, labels, policy):
    """One row per item for the given may policy (None = select-all)."""
    rows = []
    for item in items:
        facts = item["facts"]
        must = set(item["must"])
        may = set(item["omittable"])
        forbidden = set(item["forbidden"])
        if policy is None:
            selected = [f["factId"] for f in facts]
            decisions = None
            stops, refusals = [], []
        else:
            vp = dict(item["viewpoint"])
            res = n2_perspective.classify_facts(facts, vp,
                                                subject_tasks=None,
                                                may_policy=policy)
            selected = res["selectedFactIds"]
            decisions = res["decisions"]
            stops, refusals = res["stops"], res["refusals"]
        sel = set(selected)
        unknown = sel - {f["factId"] for f in facts}
        must_hits = sel & must
        recall = len(must_hits) / len(must) if must else 1.0
        precision = len(must_hits) / len(sel) if sel else None
        ground_counts = {}
        if decisions:
            for d in decisions:
                if d.get("factId"):
                    key = f"{d['class']}:{d['ground']}"
                    ground_counts[key] = ground_counts.get(key, 0) + 1
        gold_may = may
        row = {
            "itemId": item["itemId"],
            "viewpointType": item["viewpoint"]["type"],
            "facts": len(facts), "must": len(must),
            "selected": sorted(sel), "selectedCount": len(sel),
            "mustRecall": round(recall, 4),
            "mustPrecision": None if precision is None else round(precision, 4),
            "maySelectionRate": round(len(sel & gold_may) / len(gold_may), 4)
            if gold_may else None,
            "forbiddenHits": len(sel & forbidden),
            "unknownIds": sorted(unknown),
            "stops": len(stops), "refusals": len(refusals),
            "groundCounts": ground_counts,
            "gates": {"selectedNonZero": len(sel) > 0,
                      "mustRecallAtLeast095": recall >= MUST_RECALL_GATE,
                      "noInvalidIds": not unknown},
        }
        rows.append(row)
    return rows


def summarize(rows, policy_label):
    n = len(rows)
    recall_min = min(r["mustRecall"] for r in rows)
    prec = [r["mustPrecision"] for r in rows if r["mustPrecision"] is not None]
    return {
        "arm": policy_label, "items": n,
        "selectedNonZero": sum(1 for r in rows if r["gates"]["selectedNonZero"]),
        "mustRecallMin": round(recall_min, 4),
        "mustRecallMean": round(sum(r["mustRecall"] for r in rows) / n, 4),
        "mustPrecisionMean": None if not prec else
        round(sum(prec) / len(prec), 4),
        "forbiddenHits": sum(r["forbiddenHits"] for r in rows),
        "unknownIds": sum(len(r["unknownIds"]) for r in rows),
        "stops": sum(r["stops"] for r in rows),
        "refusals": sum(r["refusals"] for r in rows),
        "itemsPassingGates": sum(1 for r in rows if all(r["gates"].values())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    items = [json.loads(line) for line in
             ITEMS.read_text(encoding="utf-8").splitlines() if line.strip()]
    frozen, labels = load_frozen(FROZEN, LABELS, items)
    # sanity: the frozen labels cover every item/fact key (load_frozen
    # already enforces exactly this set)
    del labels

    select_rows = arm_rows(items, None, "select")
    omit_rows = arm_rows(items, None, "omit")
    all_rows = arm_rows(items, None, None)

    summary = {
        "selectDefault": summarize(select_rows, "perspective-rule:select"),
        "omitConservative": summarize(omit_rows, "perspective-rule:omit"),
        "selectAllBaseline": summarize(all_rows, "select-all (baseline)"),
    }
    gates = {
        "selectedNonZeroEveryItem":
            summary["selectDefault"]["selectedNonZero"] == len(items),
        "perItemMustRecallAtLeast095":
            summary["selectDefault"]["mustRecallMin"] >= MUST_RECALL_GATE,
        "noInvalidIds": summary["selectDefault"]["unknownIds"] == 0,
        "noForbiddenHits": summary["selectDefault"]["forbiddenHits"] == 0,
    }
    archive = {
        "purpose": "N2 perspective-rule acceptance over the frozen D2 dev "
                   "set (16 items / 92 facts, v3 labels via the frozen "
                   "guards); select-all reported as the labelled baseline",
        "devSetNote": "the D2 dev set calibrated the rubric — dev-set "
                      "gates, not an independent-holdout claim",
        "trackedTaskNote": "items carry no subject task list, so the "
                           "tracked-task must rule cannot fire here "
                           "(covered by pipeline unit tests S12/S14)",
        "frozenLabels": {"file": FROZEN.name,
                         "agreement": frozen.get("agreement", {})},
        "gatesPreRegistered": {
            "selectedNonZeroEveryItem": "selected facts > 0 per item",
            "perItemMustRecallAtLeast095": "per-item must recall >= 0.95",
            "noInvalidIds": "invalid/unknown fact ids == 0",
            "noForbiddenHits": "no invisible fact ever selected",
        },
        "summary": summary,
        "gates": gates,
        "pass": all(gates.values()),
        "rows": {"select": select_rows, "omit": omit_rows, "selectAll": all_rows},
    }
    pathlib.Path(args.out).write_text(
        json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps({"summary": summary, "gates": gates,
                      "pass": archive["pass"]}, ensure_ascii=False, indent=1))
    print("archive ->", args.out)
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
