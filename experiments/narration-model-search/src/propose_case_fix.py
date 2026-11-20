# -*- coding: utf-8 -*-
"""Propose (and verify on a copy) the canonical rewrite for three dev cases.

The shared package belongs to lane 01. This script never edits it. It copies the
case input in memory, applies the smallest documented mapping from the old 05
delta shape to the canonical operations, and runs the reference serializer on
the copy. If the copy serializes, the proposal is mechanically possible; 01
still owns the decision and must rebuild/publish the package hashes.

Mapping:
  * old `任务` snapshot -> `完成任务: [goals whose status is 已完成]`
    (the unchanged tasks need no delta operation)
  * bare `外貌` -> `新增外貌` (array)
  * string `解除外貌` -> `[string]`, string `新增外貌` -> `[string]`

Usage:
    python -X utf8 src/propose_case_fix.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
WORKTREE = ROOT.parent.parent
PACKAGE = pathlib.Path("D:/others/Jity/.local/parallel-local-game/results/quality/dev-package-v1")
OUT = pathlib.Path("D:/others/Jity/.local/parallel-local-game/results/11-model-search/requests/01-case-fix-proposal.json")
V2_RENDER = WORKTREE / "experiments/narration-runtime-v2/src/v2_render.py"

sys.path.insert(0, str(V2_RENDER.parent))
import v2_render  # noqa: E402

TARGETS = {
    "tide-continuity-tide-duty-t2",
    "tide-continuity-tide-duty-t3",
    "fixture-goggles-transfer",
}


def squash(value):
    if isinstance(value, str):
        return value.replace(" ", "").replace("\t", "").replace("\u3000", "")
    if isinstance(value, list):
        return [squash(item) for item in value]
    if isinstance(value, dict):
        return {key: squash(item) for key, item in value.items()}
    return value


def as_list(value):
    if isinstance(value, list):
        return value
    return [value]


def rewrite(case_id: str, block: dict) -> tuple[dict, list]:
    fixed = copy.deepcopy(block)
    notes = []
    changes = fixed.get("本回合变化", {}).get("变化", {})
    for name, change in list(changes.items()):
        if "任务" in change and isinstance(change["任务"], dict):
            tasks = change.pop("任务")
            completed = [task["目标"] for task in (tasks.get("小任务") or [])
                         if task.get("状态") == "已完成"]
            big = tasks.get("大任务")
            if big and big.get("状态") == "已完成":
                completed.append(big["目标"])
            if completed:
                change["完成任务"] = sorted(set(completed))
            notes.append(f"{name}: 任务 snapshot -> 完成任务 {change.get('完成任务', [])}")
        if "外貌" in change:
            change["新增外貌"] = as_list(change.pop("外貌"))
            notes.append(f"{name}: 外貌 -> 新增外貌")
        for field in ("新增外貌", "解除外貌", "新增个性", "解除个性"):
            if field in change and isinstance(change[field], str):
                change[field] = [change[field]]
                notes.append(f"{name}: {field} string -> array")
    return fixed, notes


def main() -> int:
    cases = [json.loads(line) for line in (PACKAGE / "cases.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    proposals = []
    for case in cases:
        if case["caseId"] not in TARGETS:
            continue
        before = case["input"]
        after, notes = rewrite(case["caseId"], before)
        record = {
            "caseId": case["caseId"],
            "category": case.get("category"),
            "changes": notes,
            "beforeDelta": before.get("本回合变化"),
            "afterDelta": after.get("本回合变化"),
        }
        try:
            text = v2_render.serialize_text(squash(after))
            record["serializerResult"] = {"ok": True, "chars": len(text),
                                          "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        except Exception as error:
            record["serializerResult"] = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        proposals.append(record)

    report = {
        "to": "01-input",
        "from": "11-model-search",
        "kind": "canonical-rewrite-proposal-verified-on-a-copy",
        "createdAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "package": {
            "manifestSha256": hashlib.sha256((PACKAGE / "manifest.json").read_bytes()).hexdigest(),
            "casesSha256": hashlib.sha256((PACKAGE / "cases.jsonl").read_bytes()).hexdigest(),
        },
        "rule": "facts/names/numbers are unchanged; only the operation names and value shapes are "
                "canonicalised. The completed-task list is derived from the old snapshot's 已完成 status.",
        "proposals": proposals,
        "decision": "01 owns the package. If this mapping is accepted, rebuild build_package.py, "
                    "recompute manifest/cases/RUBRIC hashes and PACKAGE.json, then tell 11.",
        "verification": "the serializer was run on an in-memory copy; the shared package file was not modified",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    print(json.dumps([{"caseId": p["caseId"], **p["serializerResult"]} for p in proposals], ensure_ascii=False, indent=1))
    return 0 if all(p["serializerResult"]["ok"] for p in proposals) else 1


if __name__ == "__main__":
    sys.exit(main())
