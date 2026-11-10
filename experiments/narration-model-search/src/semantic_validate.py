# -*- coding: utf-8 -*-
"""Validate structured semantic outputs against a frozen case pack.

This is the lane-11 response to the real 09 failures:
  * effect for an undeclared target,
  * a literal `id` placeholder where an entity id was required,
  * task coverage that only decided 12 of 73 rows,
  * a continuation character that was a display name or the protagonist.

It does not generate text and does not judge prose. It checks the JSON
references/coverage that 03/04's corrected prompts require, so a candidate's
structured capability can be compared separately from the narration quality
batch. A candidate is never called "bad at narration" from this report.

Pack JSONL per case:
  caseId, kind = tasks|results|continuation|updates,
  allowedIds, nameToId (optional), allowUniqueNames (bool),
  protagonistId (continuation), requiredCharacterIds,
  allowedTaskIdsByCharacter, alreadyAchievedTaskIds,
  declaredTargetIds, maxCandidates

Run dir: one <caseId>.json per case with {"caseId","text"} (screen.py layout).

Usage:
    python -X utf8 src/semantic_validate.py --pack semantic-probes/pack.jsonl \
        --run-dir evidence/runs/semantic/<model> --out <report.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

ID_KEYS = {
    "entityId", "containerId", "characterId", "targetId", "memberId",
    "sourceId", "ownerId", "taskId", "parentTaskId",
}
PLACEHOLDER_RE = re.compile(r"^(id|entity_id|task_id|人物id|角色id|<.*>|todo|tbd)$", re.I)
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def parse_json(text: str) -> tuple[object | None, str | None]:
    cleaned = FENCE_RE.sub("", (text or "").strip()).strip()
    try:
        return json.loads(cleaned), None
    except ValueError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end + 1]), "extracted_object"
            except ValueError:
                pass
    return None, "not_json"


def normalize_name(name: str) -> str:
    return re.sub(r"[\s\u3000]+", "", name)


class Checker:
    def __init__(self, case: dict):
        self.case = case
        self.allowed = set(case.get("allowedIds") or [])
        self.names = {normalize_name(key): value for key, value in (case.get("nameToId") or {}).items()}
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def resolve(self, value: str, where: str) -> str | None:
        if not isinstance(value, str) or not value:
            self.errors.append(f"{where}: empty id")
            return None
        if PLACEHOLDER_RE.match(value.strip()):
            self.errors.append(f"{where}: placeholder id {value!r}")
            return None
        if value in self.allowed:
            return value
        mapped = self.names.get(normalize_name(value))
        if mapped:
            if self.case.get("allowUniqueNames"):
                self.warnings.append(f"{where}: resolved unique name {value!r} -> {mapped}")
                return mapped
            self.errors.append(f"{where}: name {value!r} used where an id is required")
            return None
        self.errors.append(f"{where}: unknown id {value!r}")
        return None

    def walk_ids(self, value: object, path: str = "$") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                here = f"{path}.{key}"
                if key in ID_KEYS and isinstance(item, str):
                    self.resolve(item, here)
                self.walk_ids(item, here)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self.walk_ids(item, f"{path}[{index}]")

    def tasks(self, value: object) -> None:
        decisions = value.get("decisions") if isinstance(value, dict) else None
        if not isinstance(decisions, list):
            self.errors.append("tasks: decisions must be an array")
            return
        required = [str(item) for item in (self.case.get("requiredCharacterIds") or [])]
        allowed_by_character = self.case.get("allowedTaskIdsByCharacter") or {}
        already = set(self.case.get("alreadyAchievedTaskIds") or [])
        seen: set[str] = set()
        for index, raw in enumerate(decisions):
            if not isinstance(raw, dict):
                self.errors.append(f"tasks.decisions[{index}]: not an object")
                continue
            character = self.resolve(str(raw.get("characterId", "")), f"tasks.decisions[{index}].characterId")
            if character is None:
                continue
            if character in seen:
                self.errors.append(f"tasks.decisions[{index}]: duplicate decision for {character}")
                continue
            seen.add(character)
            achieved = raw.get("achieved")
            if not isinstance(achieved, list):
                self.errors.append(f"tasks.decisions[{index}].achieved: must be an array")
                continue
            allowed_tasks = set(allowed_by_character.get(character) or [])
            for task_index, task_id in enumerate(achieved):
                where = f"tasks.decisions[{index}].achieved[{task_index}]"
                resolved = self.resolve(str(task_id), where)
                if resolved is None:
                    continue
                if allowed_tasks and resolved not in allowed_tasks:
                    self.errors.append(f"{where}: {resolved} does not belong to {character}")
                if resolved in already:
                    self.errors.append(f"{where}: repeats already-achieved task {resolved}")
        missing = sorted(set(required) - seen)
        if missing:
            self.errors.append(f"tasks: character coverage {len(seen)}/{len(required)}; missing {missing}")

    def results(self, value: object) -> None:
        members = value.get("members") if isinstance(value, dict) else None
        if not isinstance(members, list) or not members:
            self.errors.append("results: members must be a non-empty array")
            return
        declared = set(self.case.get("declaredTargetIds") or [])
        for index, member in enumerate(members):
            if not isinstance(member, dict):
                self.errors.append(f"results.members[{index}]: not an object")
                continue
            member_id = self.resolve(str(member.get("memberId", "")), f"results.members[{index}].memberId")
            effects = member.get("effects")
            if not isinstance(effects, list):
                self.errors.append(f"results.members[{index}].effects: must be an array")
                continue
            for effect_index, effect in enumerate(effects):
                target = effect.get("targetId") if isinstance(effect, dict) else None
                where = f"results.members[{index}].effects[{effect_index}].targetId"
                resolved = self.resolve(str(target or ""), where)
                if resolved is not None and declared and resolved not in declared:
                    self.errors.append(f"{where}: effect for undeclared target {resolved}")
            _ = member_id

    def continuation(self, value: object) -> None:
        candidates = value.get("candidates") if isinstance(value, dict) else None
        if not isinstance(candidates, list):
            self.errors.append("continuation: candidates must be an array")
            return
        limit = int(self.case.get("maxCandidates") or 0)
        if limit and len(candidates) > limit:
            self.errors.append(f"continuation: {len(candidates)} candidates > max {limit}")
        protagonist = self.case.get("protagonistId")
        for index, raw in enumerate(candidates):
            if not isinstance(raw, dict):
                self.errors.append(f"continuation.candidates[{index}]: not an object")
                continue
            character = self.resolve(str(raw.get("characterId", "")),
                                     f"continuation.candidates[{index}].characterId")
            if character and protagonist and character == protagonist:
                self.errors.append(f"continuation.candidates[{index}]: protagonist {character} is not a continuation target")
            if not str(raw.get("text") or "").strip():
                self.errors.append(f"continuation.candidates[{index}]: empty text")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=pathlib.Path, required=True)
    parser.add_argument("--run-dir", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()

    cases = [json.loads(line) for line in args.pack.read_text(encoding="utf-8").splitlines() if line.strip()]
    reports = []
    for case in cases:
        path = args.run_dir / f"{case['caseId']}.json"
        report = {"caseId": case["caseId"], "kind": case.get("kind"), "ok": False,
                  "errors": [], "warnings": []}
        if not path.exists():
            report["errors"].append(f"missing output file {path.name}")
            reports.append(report)
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        text = record.get("text") or ""
        report["chars"] = len(text)
        report["textSha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        value, note = parse_json(text)
        if note:
            report["errors"].append(f"output is not JSON ({note})")
            reports.append(report)
            continue
        checker = Checker(case)
        kind = case.get("kind")
        if kind == "tasks":
            checker.tasks(value)
        elif kind == "results":
            checker.results(value)
        elif kind == "continuation":
            checker.continuation(value)
        elif kind == "updates":
            checker.walk_ids(value)
        else:
            checker.errors.append(f"unknown kind {kind!r}")
        report["errors"] = checker.errors
        report["warnings"] = checker.warnings
        report["ok"] = not checker.errors
        reports.append(report)

    payload = {
        "note": "structured semantic checks only; no prose quality and no product acceptance",
        "pack": str(args.pack),
        "runDir": str(args.run_dir),
        "cases": len(reports),
        "passed": sum(1 for report in reports if report["ok"]),
        "reports": reports,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if payload["passed"] == payload["cases"] else 2


if __name__ == "__main__":
    sys.exit(main())
