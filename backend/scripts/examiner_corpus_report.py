"""Examiner corpus runner and report.

Ground truth lives in tests/examiner_corpus.json; this module executes each
case against ExaminerAgent and classifies the verdict:

- false_reject   expected pass/conditional, got blocked
- false_release  expected blocked, got pass/conditional
- rule_mismatch  verdict class matches but the triggered rule set does not

Run standalone for the metrics report:

    cd backend && PYTHONUTF8=1 python scripts/examiner_corpus_report.py --label tian-734750e

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


def load_corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


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


def evaluate(ruling, expected: dict) -> tuple[bool, str, str]:
    """Return (ok, kind, detail); kind is one of pass/false_reject/false_release/rule_mismatch."""
    got = ruling.permissibility.value
    want = expected["permissibility"]
    if want == "blocked":
        if got != "blocked":
            return False, "false_release", f"期望 blocked，实际 {got}"
        return True, "pass", ""
    if got == "blocked":
        return False, "false_reject", f"期望 {want}，实际 blocked"
    want_rules = expected.get("rules")
    got_rules = sorted({r.rule_type for r in ruling.triggered_rules})
    if want_rules is not None and got_rules != sorted(want_rules):
        return False, "rule_mismatch", f"期望规则 {sorted(want_rules)}，实际 {got_rules}"
    if want_rules is None and got != want:
        # e.g. expected permissible without caring about rules, got conditional
        return False, "rule_mismatch", f"期望 {want}，实际 {got}（触发 {got_rules}）"
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
        })
    return _summarize(results)


def _summarize(results: list[dict]) -> dict:
    def ids(kind: str) -> list[str]:
        return [r["id"] for r in results if r["kind"] == kind]

    known = [r for r in results if r["known_bug"]]
    triggered = [r for r in results if r["kind"] != "rule_mismatch"]
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
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "passed": len(ids("pass")),
        "false_reject": {"count": len(ids("false_reject")), "ids": ids("false_reject")},
        "false_release": {"count": len(ids("false_release")), "ids": ids("false_release")},
        "rule_mismatch": {"count": len(ids("rule_mismatch")), "ids": ids("rule_mismatch")},
        "check_trigger": {
            "evaluable": sum(1 for r in results if r["kind"] != "rule_mismatch"),
            "verdict_correct": len(ids("pass")),
        },
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
    args = parser.parse_args()

    report = run_all()
    report["label"] = args.label

    print(f"共 {report['total']} 条：通过 {report['passed']}，"
          f"误拒 {report['false_reject']['count']}，"
          f"误放 {report['false_release']['count']}，"
          f"规则不符 {report['rule_mismatch']['count']}")
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
