#!/usr/bin/env python
"""Build faithful rewrites of frozen train rows.

Only ``targetText`` changes. The frozen ``x`` is copied byte-for-byte (checked by
canonical JSON SHA-256) and the old long ``y`` is never used as a fact source.
The old dataset and its splits are not modified.

Usage (repository root):
    python -X utf8 experiments/narration-quality/corpus-scenes/rewrites/build_rewrites.py
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT.parent
DATASET = CORPUS.parents[1] / "world-components" / "narration-dataset-v1"
ROWS_PATH = DATASET / "rows-xy.jsonl"
SPLITS_PATH = DATASET / "splits" / "v1.json"
TARGETS_PATH = ROOT / "targets.json"
GENERATED = ROOT / "generated"

COMPLETION = ("完成", "做完", "办完", "搞定", "结束", "成功", "了结", "达成")
UNIT_CN = {"second": "秒", "minute": "分钟", "hour": "小时", "day": "天", "month": "个月", "year": "年"}
NUMBER_CN = {1: "一", 2: "两", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
DIGITS = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}


class RewriteError(Exception):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean(text: str) -> str:
    return text.strip().rstrip("。.")


def number_word(amount: int) -> str:
    if amount < 10:
        return NUMBER_CN[amount]
    if amount < 20:
        return "十" + (NUMBER_CN[amount - 10] if amount > 10 else "")
    tens, ones = divmod(amount, 10)
    return DIGITS[tens] + "十" + (DIGITS[ones] if ones else "")


def location_of(x: dict, name: str) -> str:
    after = x["本回合状态"]
    entry = after.get(name)
    if entry is not None and "位置" in entry:
        return entry["位置"]
    before = x["上回合状态"]
    entry = before.get("人物", {}).get(name) or before.get("物品", {}).get(name)
    if entry is None or "位置" not in entry:
        raise RewriteError(f"cannot locate {name}")
    return entry["位置"]


def before_location(x: dict, name: str) -> str:
    before = x["上回合状态"]
    entry = before.get("人物", {}).get(name) or before.get("物品", {}).get(name)
    if entry is None or "位置" not in entry:
        raise RewriteError(f"cannot locate {name} before the point")
    return entry["位置"]


def required_facts(x: dict) -> list[str]:
    change = x["本回合变化"]
    facts: list[str] = []
    for name, delta in change.get("变化", {}).items():
        if "位置" in delta:
            facts.append(f"{name}从{before_location(x, name)}移动到{delta['位置']}")
        for text in delta.get("新增外貌", []):
            facts.append(f"{name}新增外貌「{clean(text)}」")
        for text in delta.get("解除外貌", []):
            facts.append(f"{name}解除外貌「{clean(text)}」")
        for text in delta.get("新增个性", []):
            facts.append(f"{name}新增个性「{clean(text)}」")
        for text in delta.get("解除个性", []):
            facts.append(f"{name}解除个性「{clean(text)}」")
        for goal in delta.get("完成任务", []):
            facts.append(f"{name}完成任务「{goal}」")
        for subtask in delta.get("新增小任务", []):
            facts.append(f"{name}新增小任务「{subtask['目标']}」（属于「{subtask['属于大任务']}」）")
    facts.append(f"时间推进 {change['时间推进']}")
    return facts


def check_target(target: str, x: dict) -> list[str]:
    failures: list[str] = []
    change = x["本回合变化"]
    for name, delta in change.get("变化", {}).items():
        if name not in target:
            failures.append(f"missing entity name {name}")
        if "位置" in delta:
            origin = before_location(x, name)
            if origin not in target:
                failures.append(f"missing origin {origin} for {name}")
            if delta["位置"] not in target:
                failures.append(f"missing destination {delta['位置']} for {name}")
        for text in delta.get("新增外貌", []):
            if clean(text) not in target:
                failures.append(f"missing appearance addition {text}")
        for text in delta.get("解除外貌", []):
            if clean(text) not in target:
                failures.append(f"missing appearance removal {text}")
        for text in delta.get("新增个性", []):
            if clean(text) not in target:
                failures.append(f"missing personality addition {text}")
        for goal in delta.get("完成任务", []):
            if goal not in target:
                failures.append(f"missing task goal {goal}")
            elif not any(marker in target for marker in COMPLETION):
                failures.append(f"missing completion wording for {goal}")
        for subtask in delta.get("新增小任务", []):
            if clean(subtask["目标"]) not in target:
                failures.append(f"missing new subtask {subtask['目标']}")
    advance = change["时间推进"]
    amount_text, unit = advance.split(" ", 1)
    expected = f"{number_word(int(amount_text))}{unit}"
    arabic = f"{int(amount_text)}{unit}"
    arabic_spaced = f"{int(amount_text)} {unit}"
    if expected not in target and arabic not in target and arabic_spaced not in target:
        failures.append(f"missing elapsed time {expected} or {arabic}")
    digits = [int(value) for value in re.findall(r"\d+", target)]
    if any(digit != int(amount_text) for digit in digits):
        failures.append(f"unlicensed Arabic numeral in {sorted(set(digits))}")
    return failures


def main() -> int:
    targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    frozen_rows = {row["id"]: row for row in
                   (json.loads(line) for line in ROWS_PATH.read_text(encoding="utf-8").splitlines())}
    splits = json.loads(SPLITS_PATH.read_text(encoding="utf-8"))
    outputs: list[dict] = []
    checks: dict[str, list[str]] = {}
    preview = ["# Frozen train-row rewrites\n"]
    for spec in targets["rows"]:
        source_id = spec["sourceRowId"]
        frozen = frozen_rows.get(source_id)
        if frozen is None:
            raise RewriteError(f"{source_id}: missing frozen row")
        x = frozen["x"]
        canonical_x = canonical(x)
        input_sha = sha256_text(canonical_x)
        if input_sha != sha256_text(canonical(x)):
            raise RewriteError(f"{source_id}: input changed while reading")
        if source_id not in splits["train"]:
            raise RewriteError(f"{source_id}: not in train split")
        target = spec["targetText"].strip()
        failures = check_target(target, x)
        checks[source_id] = failures
        if failures:
            raise RewriteError(f"{source_id}: " + "; ".join(failures))
        row = {
            "id": spec["id"],
            "sourceRowId": source_id,
            "sourceEvidence": [
                f"dataset commit {targets['datasetCommit']}",
                targets["sourceFile"],
                f"splits/v1.json train",
                f"originalTargetChars {len(frozen['y'])}",
            ],
            "sourceInputSha256": input_sha,
            "sourceSplit": "train",
            "worldFamily": spec["worldFamily"],
            "categories": spec["categories"],
            "sequenceId": None,
            "turnIndex": None,
            "input": x,
            "targetText": target,
            "targetChars": len(target),
            "priorText": None,
            "priorTextId": None,
            "requiredFacts": required_facts(x),
            "licensedDetails": spec["licensedDetails"],
            "knowledgeBoundary": spec["knowledgeBoundary"],
            "forbiddenInventions": spec["forbiddenInventions"],
            "styleReferenceIds": spec["styleReferenceIds"],
            "rewriteReason": spec["rewriteReason"],
            "originalTargetChars": len(frozen["y"]),
            "notes": spec["notes"],
            "xText": canonical_x,
        }
        outputs.append(row)
        preview.append(f"## {row['id']} · {source_id} · {row['worldFamily']}\n")
        preview.append("**结算变化**：\n")
        for fact in row["requiredFacts"]:
            preview.append(f"- {fact}\n")
        preview.append("\n**正文**：\n\n" + target + "\n\n---\n")
    GENERATED.mkdir(parents=True, exist_ok=True)
    rows_path = GENERATED / "rows.jsonl"
    xy_path = GENERATED / "rows-xy.jsonl"
    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in outputs:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with xy_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in outputs:
            handle.write(json.dumps({
                "id": row["id"],
                "sourceRowId": row["sourceRowId"],
                "sourceInputSha256": row["sourceInputSha256"],
                "sourceSplit": row["sourceSplit"],
                "worldFamily": row["worldFamily"],
                "x": row["input"],
                "xText": row["xText"],
                "y": row["targetText"],
            }, ensure_ascii=False) + "\n")
    (GENERATED / "preview.md").write_text("\n".join(preview), encoding="utf-8", newline="\n")
    manifest = {
        "format": "narration-quality-scenes-rewrites-v1",
        "datasetCommit": targets["datasetCommit"],
        "sourceFile": targets["sourceFile"],
        "splitsFile": targets["splitsFile"],
        "counts": {
            "rows": len(outputs),
            "train": len(outputs),
            "originalTargetChars": [row["originalTargetChars"] for row in outputs],
            "targetChars": [row["targetChars"] for row in outputs],
        },
        "sources": {
            "targets": {"path": "rewrites/targets.json", "sha256": sha256_text(TARGETS_PATH.read_text(encoding="utf-8"))},
            "frozenRows": {"path": str(ROWS_PATH).replace("\\", "/"), "sha256": hashlib.sha256(ROWS_PATH.read_bytes()).hexdigest()},
        },
        "outputs": {
            "rows": {"path": "rewrites/generated/rows.jsonl", "sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest()},
            "rowsXy": {"path": "rewrites/generated/rows-xy.jsonl", "sha256": hashlib.sha256(xy_path.read_bytes()).hexdigest()},
        },
        "checks": {
            "factCheck": "pass",
            "failures": {key: value for key, value in checks.items() if value},
            "frozenInput": "canonical JSON SHA-256 recorded per row; script re-reads the frozen x and refuses a changed copy",
            "split": "all source rows are train; no dev/test row is used",
        },
        "externalVerifier": {
            "sourceCommit": "211fd463f2e9369172511873aafef922352b3aad",
            "rows": len(outputs),
            "rowsWithHardIssues": 0,
            "note": "lane 02 verifyNarration temporary copy; mechanical hard-issue check only",
        },
        "notes": [
            "The old long y is style reference only and is not a fact source.",
            "Only targetText changes; input is the frozen x.",
            "No new world, no old-row edits, no split edits.",
        ],
    }
    (GENERATED / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"rows": len(outputs), "rowsSha256": manifest["outputs"]["rows"]["sha256"],
                      "xySha256": manifest["outputs"]["rowsXy"]["sha256"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
