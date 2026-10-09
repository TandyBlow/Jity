"""Examiner corpus runner and report.

Ground truth lives in tests/examiner_corpus.json; this module executes each
case against ExaminerAgent and reports three separated measurements:

- 测试集通过率 (suite pass rate) — development-facing. The corpus is built
  around known defects, so its sample distribution does NOT represent real
  player input; never quote this as 玩家行动判定准确率.
- 可行性判定 (permissibility verdict) — correct/total over every case.
- 规则触发 (rule triggering) — micro Precision/Recall over the rule-type
  sets of all cases that carry a rule expectation and are not expected to
  be blocked. Cases falsely rejected still report their collected rules,
  so they stay in the denominator; the JSON per-case records keep the
  full detail either way.

Development diff counters (false_reject / false_release / rule_mismatch)
stay for triage; for thesis numbers use permissibility + rules P/R and the
known_bug section, not the pytest suite status (known_bug cases xfail).

Run standalone:

    cd backend && PYTHONUTF8=1 python scripts/examiner_corpus_report.py --label fyp-base-ad29b2d

`--out` additionally writes the report as JSON (artifacts/ dir recommended).
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.agents.examiner import ExaminerAgent  # noqa: E402
from app.services.game_state.entry_state import EntryStateMixin  # noqa: E402

CORPUS_PATH = Path(__file__).resolve().parents[1] / "tests" / "examiner_corpus.json"
# merge_entry_state expects a fully initialized base_state (as the session
# payload carries one); D cases start from the same neutral shape.
_BASE_STATE = {
    "turn": 0,
    "current_location": "",
    "items": [],
    "npcs": [],
    "quests": [],
    "world_facts": [],
    "recent_events": [],
    "_scene_prompt": "",
    "player_status": {
        "condition": "正常", "danger_level": "medium",
        "current_goal": "", "notes": "",
    },
}


class _EntryStateOnly(EntryStateMixin):
    """D cases carry no entry npcs, so merge_by_name must never be reached."""

    def merge_by_name(self, *args, **kwargs):
        raise AssertionError("entry cases must not include npcs")


def load_corpus(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or CORPUS_PATH).read_text(encoding="utf-8"))


def merged_entry_state(entry: dict) -> dict:
    campaign = SimpleNamespace(
        starting_state=None,
        arcs=[SimpleNamespace(
            goal="了解当前处境",
            sessions=[SimpleNamespace(name="报到日", entry_state=entry)],
        )],
    )
    import copy
    return _EntryStateOnly().merge_entry_state(
        copy.deepcopy(_BASE_STATE), campaign, 0, 0, initialize=True
    )


def run_case(case: dict, fixtures: dict):
    state = merged_entry_state(case["entry"]) if "entry" in case else fixtures[case["fixture"]]
    return asyncio.run(ExaminerAgent().examine(case["action"], state))


def _got_rules(ruling) -> list[str]:
    return sorted({r.rule_type for r in ruling.triggered_rules})


def evaluate(ruling, expected: dict) -> tuple[bool, str, str]:
    """Return (ok, kind, detail); kind is one of pass/false_reject/false_release/rule_mismatch.

    Permissibility is compared first and unconditionally; the rule-set
    comparison only ever refines a verdict-consistent result.
    """
    got = ruling.permissibility.value
    want = expected["permissibility"]
    if want == "blocked":
        if got != "blocked":
            return False, "false_release", f"期望 blocked，实际 {got}"
        return True, "pass", ""
    if got == "blocked":
        return False, "false_reject", f"期望 {want}，实际 blocked"
    got_rules = _got_rules(ruling)
    if got != want:
        return False, "rule_mismatch", f"判定应为 {want}，实际 {got}；规则实际 {got_rules}"
    want_rules = expected.get("rules")
    if want_rules is not None and got_rules != sorted(want_rules):
        return False, "rule_mismatch", f"期望规则 {sorted(want_rules)}，实际 {got_rules}"
    return True, "pass", ""


def run_all(corpus: dict | None = None) -> dict:
    corpus = corpus or load_corpus()
    fixtures = corpus["fixtures"]
    results = []
    for case in corpus["cases"]:
        ruling = run_case(case, fixtures)
        ok, kind, detail = evaluate(ruling, case["expected"])
        results.append({
            "id": case["id"], "category": case["category"],
            "action": case["action"], "ok": ok, "kind": kind,
            "detail": detail, "known_bug": bool(case.get("known_bug")),
            "expected_permissibility": case["expected"]["permissibility"],
            "got_permissibility": ruling.permissibility.value,
            "expected_rules": case["expected"].get("rules"),
            "got_rules": _got_rules(ruling),
        })
    return _summarize(results)


def _summarize(results: list[dict]) -> dict:
    def ids(kind: str) -> list[str]:
        return [r["id"] for r in results if r["kind"] == kind]

    perm_correct = sum(1 for r in results if r["got_permissibility"] == r["expected_permissibility"])

    rule_cases = [r for r in results
                  if r["expected_rules"] is not None and r["expected_permissibility"] != "blocked"]
    tp = pred = exp = 0
    for r in rule_cases:
        want_set, got_set = set(r["expected_rules"]), set(r["got_rules"])
        tp += len(want_set & got_set)
        pred += len(got_set)
        exp += len(want_set)

    categories: dict[str, dict] = {}
    for r in results:
        bucket = categories.setdefault(r["category"], {
            "total": 0, "passed": 0, "false_reject": 0, "false_release": 0, "rule_mismatch": 0,
        })
        bucket["total"] += 1
        if r["ok"]:
            bucket["passed"] += 1
        else:
            bucket[r["kind"]] += 1

    known = [r for r in results if r["known_bug"]]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "passed": len(ids("pass")),
        "permissibility": {
            "total": len(results),
            "correct": perm_correct,
            "accuracy": round(perm_correct / len(results), 4) if results else None,
        },
        "rules": {
            "cases_with_expectation": len(rule_cases),
            "true_positives": tp,
            "predicted": pred,
            "expected": exp,
            "precision": round(tp / pred, 4) if pred else None,
            "recall": round(tp / exp, 4) if exp else None,
        },
        "false_reject": {"count": len(ids("false_reject")), "ids": ids("false_reject")},
        "false_release": {"count": len(ids("false_release")), "ids": ids("false_release")},
        "rule_mismatch": {"count": len(ids("rule_mismatch")), "ids": ids("rule_mismatch")},
        "by_category": categories,
        "known_bug": {
            "failing": [r["id"] for r in known if not r["ok"]],
            "passing": [r["id"] for r in known if r["ok"]],
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="", help="version label recorded in the report")
    parser.add_argument("--out", default="", help="optional path for the JSON report")
    parser.add_argument("--corpus", default="", help="corpus JSON path (default: the dev corpus)")
    args = parser.parse_args()

    report = run_all(load_corpus(args.corpus) if args.corpus else None)
    report["label"] = args.label

    perm, rules = report["permissibility"], report["rules"]
    print(f"共 {report['total']} 条：人工测试集通过 {report['passed']}"
          f"（开发回归口径——语料围绕已知缺陷构建，不代表真实玩家输入分布，"
          f"不可引用为玩家行动判定准确率）")
    print(f"可行性判定：{perm['correct']}/{perm['total']}（{perm['accuracy']}）")
    if rules["cases_with_expectation"]:
        print(f"规则触发（{rules['cases_with_expectation']} 条有标注）："
              f"Precision {rules['true_positives']}/{rules['predicted']}"
              f"（{rules['precision']}），"
              f"Recall {rules['true_positives']}/{rules['expected']}"
              f"（{rules['recall']}）")
    for kind in ("false_reject", "false_release", "rule_mismatch"):
        entry = report[kind]
        if entry["count"]:
            print(f"  {kind}: {'、'.join(entry['ids'])}")
    known = report["known_bug"]
    print(f"known_bug 未修复 {len(known['failing'])} 条（{'、'.join(known['failing']) or '无'}），"
          f"已修复待删标志 {len(known['passing'])} 条（{'、'.join(known['passing']) or '无'}）")
    print("分组：")
    for cat, bucket in report["by_category"].items():
        print(f"  {cat}: {bucket['passed']}/{bucket['total']} 通过"
              + (f"（误拒 {bucket['false_reject']}、误放 {bucket['false_release']}、"
                 f"规则 {bucket['rule_mismatch']}）" if bucket["passed"] < bucket["total"] else ""))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入 {out}")


if __name__ == "__main__":
    main()
