# Batch-1 legal-input unit extension regression (world-components commit 1,
# coordinator batch order: fix rendering exceptions on legal `second` /
# zero-duration inputs). The shared renderer (n4_render.py) previously
# KeyError'd on the four TimeAdvance units the frozen corpus happens not to
# cover and ValueError'd on amount 0; the judge (corpus_check.py) only
# parsed 分钟/小时. Both now cover the full legal space (six units, amount
# ≥ 0). Three proofs before anything new is judged:
#
#   1. legacy byte equality — every plan in the frozen corpus and the
#      frozen holdout renders BYTE-IDENTICAL under the old and the extended
#      renderer, so no frozen rendering, training input or fixture token
#      count moves;
#   2. archived re-judge — every archived r3-direction holdout model output
#      (44 unseen + 1 regression, both arms) gets the SAME verdict class
#      under the extended judge as recorded in the frozen eval archive;
#   3. new-space end-to-end — second/zero/day/month/year rows render,
#      judge to pass when the text agrees with the plan and to review when
#      it disagrees (never fail-silent, never auto-pass).
#
# The signed freeze record freeze-r3-direction.json pins the OLD renderer
# and judge hashes; it is kept untouched for provenance. This script
# records old+new hashes so the amendment can be re-verified; the artifact
# it writes is the evidence for the amendment round.

import argparse
import copy
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from n4_render import render_input, num_cn, UNIT_CN  # noqa: E402
import corpus_check  # noqa: E402

REPO = HERE.parent.parent.parent

# frozen hashes (n4-offline-package-r3-direction.json / freeze-r3-direction)
OLD_RENDERER_SHA = "65bfe89adfbb75d5637d3661cab383aa9bc678dffb97ab5eb8a0d28ac1e3f2ef"
OLD_JUDGE_SHA = "e16bd2c98a7141aaf8251c6562f191eb78809840e477e2b24f8345ecd351ac50"


def sha_file(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# ---- the OLD renderer, reproduced verbatim for the equality proof --------

OLD_UNIT_CN = {"minute": "分钟", "hour": "小时"}
OLD_CN_DIGITS = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
                 7: "七", 8: "八", 9: "九"}


def old_num_cn(amount: int) -> str:
    if not (1 <= amount <= 99):
        raise ValueError(f"num_cn out of range: {amount}")
    tens, ones = divmod(amount, 10)
    if tens == 0:
        return "两" if amount == 2 else OLD_CN_DIGITS[amount]
    if tens == 1:
        return "十" + (OLD_CN_DIGITS[ones] if ones else "")
    head = OLD_CN_DIGITS[tens] + "十"
    return head if ones == 0 else head + OLD_CN_DIGITS[ones]


def old_render_entry(e: dict) -> str:
    kind = e["kind"]
    if kind == "moved":
        return f"位置：{e['name']} 从{e['from']}到{e['to']}"
    if kind == "task_achieved":
        return f"任务达成：{e['name']}「{e['goal']}」"
    if kind == "personality_changed":
        return f"个性：{e['name']}{e['text']}"
    if kind == "sanity_changed":
        direction = ("上升" if e["to"] > e["from"]
                     else "下降" if e["to"] < e["from"] else "不变")
        return f"理智：{e['name']} {e['from']}→{e['to']}（{direction}）"
    if kind == "appearance_changed":
        return f"外貌：{e['name']} {e['text']}"
    if kind == "positioned_at":
        return f"现状：{e['name']} 已在{e['at']}"
    if kind == "time":
        return f"时间推进：约{old_num_cn(e['amount'])}{OLD_UNIT_CN[e['unit']]}"
    if kind == "no_change":
        return "无变化"
    raise ValueError(f"unknown plan kind {kind}")


def old_render_input(plan: list) -> str:
    lines = [f"{i + 1}. {old_render_entry(e)}" for i, e in enumerate(plan)]
    return "叙事生成任务。\n事实：\n" + "\n".join(lines) + "\n正文："


def load_jsonl(path: pathlib.Path) -> list:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def proof_legacy_byte_equality() -> dict:
    """Every frozen plan renders identically under old and new renderer."""
    sources = {
        "corpus.seeds.jsonl": load_jsonl(HERE / "corpus.seeds.jsonl"),
        "rewrites.jsonl": load_jsonl(HERE / "rewrites.jsonl"),
        "holdout.jsonl": load_jsonl(HERE.parent / "n4_holdout" / "holdout.jsonl"),
    }
    counts, mismatches, covered = {}, [], set()
    for name, rows in sources.items():
        same = 0
        for r in rows:
            text_new = render_input(r["plan"])
            text_old = old_render_input(r["plan"])
            if text_new != text_old:
                mismatches.append(f"{name}:{r.get('sourceGroupId')}")
            same += 1
            for e in r["plan"]:
                if e.get("kind") == "time":
                    covered.add((e["amount"], e["unit"]))
        counts[name] = same
    return {"plansChecked": counts, "mismatches": mismatches,
            "frozenTimeEntries": sorted(covered), "pass": not mismatches}


def proof_archived_rejudge() -> dict:
    """Re-judge archived holdout outputs under the extended judge; verdict
    classes must equal the frozen archive byte for byte."""
    # the eval module parses sys.argv at import time (r1 corpus-pin guard);
    # the regression never infers, so pin the tag the archive was written with
    sys.argv = [sys.argv[0], "--run-tag", "r3-direction"]
    import eval_n4_finetune as ev
    holdout_path = HERE.parent / "n4_holdout" / "holdout.jsonl"
    units = ev.load_holdout_inputs(holdout_path, ev.load_corpus_rows())
    by_input = {u["input"]: u["row"] for u in units}
    archive = json.loads((REPO / "artifacts" / "world-components" /
                          "n4-holdout-eval-r3-direction.json").read_text(encoding="utf-8"))
    compared, diffs = 0, []
    for arm in ("base", "finetuned"):
        for scope in ("unseen", "regression"):
            for item in archive["arms"][arm]["results"][scope]:
                row = by_input.get(item["input"])
                if row is None:
                    diffs.append(f"{arm}/{scope}: input not in holdout units")
                    continue
                redone = ev.judge(row, item["output"])
                compared += 1
                if redone["verdict"] != item["verdict"]:
                    diffs.append(f"{arm}/{scope}:{item['devGroups']}: "
                                 f"archived={item['verdict']} redone={redone['verdict']}")
    return {"archivedVerdictsRejudged": compared,
            "unitMergedInputs": len(units),
            "diffs": diffs, "pass": not diffs}


def _row_with_time(base_row: dict, amount: int, unit: str) -> dict:
    row = copy.deepcopy(base_row)
    for scope in ("plan", "fullPlan"):
        for e in row[scope]:
            if e.get("kind") == "time":
                e["amount"], e["unit"] = amount, unit
    row["hashes"]["plan"] = hashlib.sha256(
        corpus_check.canon(row["plan"]).encode("utf-8")).hexdigest()
    row["hashes"]["fullPlan"] = hashlib.sha256(
        corpus_check.canon(row["fullPlan"]).encode("utf-8")).hexdigest()
    return row


def proof_new_space(rows: list) -> dict:
    """Render + judge the extended space: seconds, zero, day/month/year."""
    loc1 = next(r for r in rows if r["sourceGroupId"] == "n4-loc-001")
    cases = [
        (40, "second", "陈舟从东门来到了钟楼。前后大约四十秒。", "pass"),
        (0, "minute", "陈舟从东门来到了钟楼。前后零分钟。", "pass"),
        (0, "second", "陈舟从东门来到了钟楼。前后零秒。", "pass"),
        (3, "day", "陈舟从东门来到了钟楼。前后三天。", "pass"),
        (6, "month", "陈舟从东门来到了钟楼。前后六个月。", "pass"),
        (1, "year", "陈舟从东门来到了钟楼。前后一年。", "pass"),
        (120, "minute", "陈舟从东门来到了钟楼。前后120分钟。", "pass"),
        (40, "minute", "陈舟从东门来到了钟楼。前后大约四十秒。", "review"),
        (3, "minute", "陈舟从东门来到了钟楼。前后零分钟。", "review"),
    ]
    results = []
    for amount, unit, text, expected in cases:
        rendered = render_input(_row_with_time(loc1, amount, unit)["plan"])
        row = _row_with_time(loc1, amount, unit)
        row["text"] = text
        sentences = [s for s in text.split("。") if s.strip()]
        all_refs = [e["ref"] for e in row["plan"]]
        row["planRefs"] = [all_refs for _ in sentences]
        row["mustExpress"] = list(all_refs)
        row["hashes"]["text"] = corpus_check.sha(text)
        fails, reviews = corpus_check.check_row(row)
        verdict = "fail" if fails else ("review" if reviews else "pass")
        results.append({"amount": amount, "unit": unit, "expected": expected,
                        "got": verdict, "renderedTail": rendered.splitlines()[-2],
                        "pass": verdict == expected})
    return {"cases": results,
            "pass": all(x["pass"] for x in results)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None,
                        help="artifact JSON path (default: print only)")
    args = parser.parse_args()

    old_renderer_sha = sha_file(HERE / "n4_render.py")
    # the OLD hash proves this file is not the frozen one; equality of the
    # current file against the frozen one would mean the fix never landed
    if old_renderer_sha == OLD_RENDERER_SHA:
        print("n4_render.py still has the frozen hash - the unit extension "
              "is absent; refusing to write an amendment evidence file")
        return 2

    corpus_rows = load_jsonl(HERE / "corpus.seeds.jsonl") + \
        load_jsonl(HERE / "rewrites.jsonl")
    eq = proof_legacy_byte_equality()
    rejudge = proof_archived_rejudge()
    new_space = proof_new_space(corpus_rows)

    archive = {
        "purpose": "batch-1 legal-input unit extension regression: renderer "
                   "and judge extended to all six TimeAdvance units and "
                   "amount 0 with legacy-space byte equality proven",
        "renderFix": {
            "oldSha256": OLD_RENDERER_SHA,
            "newSha256": old_renderer_sha,
            "scope": "UNIT_CN gains second/day/month/year (mirrors the "
                     "frontend narration-split UNIT_CN table); num_cn "
                     "accepts 0 (零) and >=100 Arabic digits; the frozen "
                     "corpus space (minute/hour x 1..99) is byte-identical",
        },
        "judgeFix": {
            "oldSha256": OLD_JUDGE_SHA,
            "newSha256": sha_file(HERE / "corpus_check.py"),
            "scope": "UNIT_EN + time-pattern alternation + masked_bigrams "
                     "gain 秒/天/个月/年; minute/hour matching unchanged; "
                     "self-test extended with new-unit positive and "
                     "mismatch rows (23 negative + 3 equivalence)",
        },
        "corpusUnchanged": {
            "corpus.seeds.jsonl": sha_file(HERE / "corpus.seeds.jsonl"),
            "rewrites.jsonl": sha_file(HERE / "rewrites.jsonl"),
            "holdout.jsonl": sha_file(HERE.parent / "n4_holdout" / "holdout.jsonl"),
        },
        "proofs": {"legacyByteEquality": eq, "archivedRejudge": rejudge,
                   "newSpaceEndToEnd": new_space},
        "freezeRecordNote": "freeze-r3-direction.json pins the OLD renderer/"
                            "judge hashes and is kept untouched for "
                            "provenance; this file is the amendment "
                            "evidence for the reviewer to re-verify",
        "pass": eq["pass"] and rejudge["pass"] and new_space["pass"],
    }
    text = json.dumps(archive, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(text[:2000])
    # the JSON print above is truncated for terminal use; judge by this line
    print("units-regression:", "PASS" if archive["pass"] else "FAIL")
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
