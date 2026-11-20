# N2 must-precision / must-recall RECOMPUTE (joint decision D1).
#
# D1 replaces the old `target` exact-match judge with:
#   - must recall >= 0.95 (hard)
#   - must precision >= 0.85
#   - may (omittable) selection rate is REPORTED, not gated
#   - target exact match is a DIAGNOSTIC only
#
# This script performs the ONLY numeric action allowed in this round: it
# re-judges the ALREADY ARCHIVED arm outputs (P0 select-all, P1-rule,
# P1-labels reference, Randeng M1a/M1b, Qwen M2) against the same v2 item
# labels. It does NOT call any model and does NOT create new predictions.
#
# `may` facts are the v2 `omittable` set. A selected may fact counts as a
# must false positive under must precision (that is exactly why the
# all-visible rule arm is over-selecting under D1), while the may selection
# RATE itself is reported separately.
#
# Usage: python experiments/world-components/n2_selection/recompute_must.py
# Output: artifacts/world-components/n2-must-r1.json

import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
ITEMS = HERE / "items.jsonl"
ARCHIVE = REPO / "artifacts" / "world-components" / "n2-selection-r2.json"
QWEN_RAW = HERE / "qwen-raw.json"
REPORT = REPO / "artifacts" / "world-components" / "n2-must-r1.json"

ARMS = [
    ("P0-program-select-all", "program", "select-all"),
    ("P1-labels-reference", "reference", "reads answer labels; reference only"),
    ("P1-rule-program", "program", "viewpoint + fact locations only"),
    ("M1a-randeng-zero-shot", "model", "Randeng-T5-77M zero-shot, instruction-after-data"),
    ("M1b-randeng-zero-shot", "model", "Randeng-T5-77M zero-shot, answer-slot"),
    ("M2-qwen3-0.6b-zero-shot", "model", "Qwen3-0.6B zero-shot, real Edge + wllama"),
]


def sha_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                       text=True).strip()
    except Exception:
        return "unknown"


def load_items() -> list:
    return [json.loads(line) for line in
            ITEMS.read_text(encoding="utf-8").splitlines() if line.strip()]


def judge(item: dict, selected: set) -> dict:
    must = set(item["must"])
    may = set(item["omittable"])
    forbidden = set(item["forbidden"])
    target = set(item["target"])
    sel = set(selected)
    unknown = sel - {f["factId"] for f in item["facts"]}
    must_hits = len(sel & must)
    must_recall = must_hits / len(must) if must else 1.0
    must_precision = must_hits / len(sel) if sel else None
    may_hits = len(sel & may)
    may_rate = may_hits / len(may) if may else None
    forbidden_hits = len(sel & forbidden)
    target_precision = len(sel & target) / len(sel) if sel else 0.0
    target_recall = len(sel & target) / len(target) if target else 0.0
    target_f1 = (2 * target_precision * target_recall / (target_precision + target_recall)
                 if (target_precision + target_recall) else 0.0)
    return {
        "selectedCount": len(sel),
        "totalFacts": len(item["facts"]),
        "mustCount": len(must),
        "selectedMustCount": must_hits,
        "mustRecall": round(must_recall, 3),
        "mustPrecision": None if must_precision is None else round(must_precision, 3),
        "maySelectedCount": may_hits,
        "mayCount": len(may),
        "maySelectionRate": None if may_rate is None else round(may_rate, 3),
        "forbiddenHits": forbidden_hits,
        "targetExact": sel == target,
        "targetPrecision": round(target_precision, 3),
        "targetRecall": round(target_recall, 3),
        "targetF1": round(target_f1, 3),
        "unknownIds": sorted(unknown),
        # D1 per-item pass: recall hard, must precision hard, no forbidden
        # selection, no unknown id. Empty selection fails precision.
        "d1ItemPass": (must_recall >= 0.95
                       and must_precision is not None and must_precision >= 0.85
                       and forbidden_hits == 0 and not unknown),
    }


def summarize(rows: list) -> dict:
    n = len(rows)
    selected = sum(r["selectedCount"] for r in rows)
    must_total = sum(r["mustCount"] for r in rows)
    must_hits = sum(r["selectedMustCount"] for r in rows)
    may_total = sum(r["mayCount"] for r in rows)
    may_hits = sum(r["maySelectedCount"] for r in rows)
    with_precision = [r for r in rows if r["mustPrecision"] is not None]
    with_may = [r for r in rows if r["maySelectionRate"] is not None]
    return {
        "items": n,
        "d1ItemsPass": sum(1 for r in rows if r["d1ItemPass"]),
        "mustRecallMean": round(sum(r["mustRecall"] for r in rows) / n, 3),
        "mustRecallMicro": round(must_hits / must_total, 3) if must_total else None,
        "mustPrecisionMean": round(sum(r["mustPrecision"] for r in with_precision) / len(with_precision), 3)
                              if with_precision else None,
        "mustPrecisionMicro": round(must_hits / selected, 3) if selected else None,
        "emptySelectionItems": sum(1 for r in rows if r["selectedCount"] == 0),
        "maySelectionRateMean": round(sum(r["maySelectionRate"] for r in with_may) / len(with_may), 3)
                                if with_may else None,
        "maySelectionRateMicro": round(may_hits / may_total, 3) if may_total else None,
        "forbiddenHitsTotal": sum(r["forbiddenHits"] for r in rows),
        "targetExactItems": sum(1 for r in rows if r["targetExact"]),
        "targetF1Mean": round(sum(r["targetF1"] for r in rows) / n, 3),
        "invalidItems": sum(1 for r in rows if r["invalid"]),
    }


def main() -> None:
    items = load_items()
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    by_item = {it["itemId"]: it for it in items}
    out_arms = {}
    for name, role, note in ARMS:
        if name not in archive["arms"]:
            sys.exit(f"arm {name} missing from {ARCHIVE}")
        rows = []
        for row in archive["arms"][name]["rows"]:
            item = by_item[row["itemId"]]
            selected = set(row["selected"])
            rows.append({"itemId": item["itemId"],
                         "invalid": row.get("invalid"),
                         **judge(item, selected)})
        out_arms[name] = {"role": role, "note": note,
                          "summary": summarize(rows), "rows": rows}
        print(f"{name}: {json.dumps(out_arms[name]['summary'], ensure_ascii=False)}")

    report = {
        "purpose": ("N2 must-precision / must-recall recompute from archived arm "
                    "outputs under joint decision D1; no model call, no new prediction"),
        "decision": "D1",
        "rule": {
            "mustRecall": ">= 0.95 per item (hard)",
            "mustPrecision": ">= 0.85 per item (must hits / all selected)",
            "maySelectionRate": "reported only, not gated",
            "targetExact": "diagnostic only",
            "forbiddenHits": "hard 0 (viewpoint-invisible facts)",
            "unknownIds": "hard 0",
        },
        "definition": {
            "must": "item['must'] (v2 program labels; v3 human annotation pending)",
            "may": "item['omittable'] (v2); a selected may fact is a must false positive",
            "target": "item['target'] (diagnostic only)",
        },
        "labelsStatus": ("v2 program labels. v3 independent annotation is not frozen; "
                         "these numbers are the D1 baseline, not a v3 verdict."),
        "provenance": {
            "items": sha_file(ITEMS),
            "archive": sha_file(ARCHIVE),
            "qwenRaw": sha_file(QWEN_RAW) if QWEN_RAW.exists() else None,
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "generatedFromCommit": git_commit(),
        },
        "arms": out_arms,
        "disclaimers": [
            "pure recompute: the selected fact ids come from the r2 archive; no inference was run",
            "P1-labels reads the answer key and is a reference row, not a model",
            "M1a/M1b are two prompt shapes of the same Randeng arm; do not add their denominators",
            "must precision treats every selected may fact as a false positive, by D1",
            "no arm is declared passed: v3 labels are not frozen and no N2 training has run",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
