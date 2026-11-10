#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pre-HPC verification of one prepared batch.

Checks, before any model output exists:
  - shared package manifest / cases / rubric hashes match the batch config;
  - every selected case's `inputSha256` matches the manifest under the package
    builder's canonicalization (`json.dumps(..., ensure_ascii=False,
    sort_keys=True)`);
  - `expected.jsonl` carries the same input and never carries `reference`;
  - every request's `userPromptSha256` matches and its seed set matches config;
  - no 12-character substring of any case reference appears in any prompt
    (reference leak check; the reference is not otherwise used).

Exit 1 on any mismatch. No model is loaded here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.abspath(os.path.join(HERE, ".."))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def load_json(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: str):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def canonical_input_sha(value) -> str:
    return sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def fail(message: str) -> None:
    print("FAIL " + message)
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()

    config_path = os.path.join(EXP, "configs", args.batch + ".json")
    config = load_json(config_path)
    pack_root = config["sharedPack"]["root"]
    manifest_path = os.path.join(pack_root, "manifest.json")
    cases_path = os.path.join(pack_root, "cases.jsonl")
    rubric_path = os.path.join(pack_root, "RUBRIC.md")

    checks = []

    def check(name: str, actual: str, expected: str) -> None:
        if actual != expected:
            fail("%s sha256 %s != %s" % (name, actual, expected))
        checks.append((name, actual))

    check("manifest", sha256_bytes(open(manifest_path, "rb").read()),
          config["sharedPack"]["manifestSha256"])
    check("cases", sha256_bytes(open(cases_path, "rb").read()),
          config["sharedPack"]["casesSha256"])
    if os.path.exists(rubric_path):
        check("rubric", sha256_bytes(open(rubric_path, "rb").read()),
              config["sharedPack"]["rubricSha256"])

    manifest = load_json(manifest_path)
    check("manifest.files.cases", manifest["files"]["cases.jsonl"],
          config["sharedPack"]["casesSha256"])
    manifest_by_id = {row["caseId"]: row for row in manifest["cases"]}
    rows = {row["caseId"]: row for row in load_jsonl(cases_path)}
    expected = {row["caseId"]: row for row in load_jsonl(
        os.path.join(EXP, "data", args.batch, "expected.jsonl"))}
    requests = load_jsonl(os.path.join(EXP, "data", args.batch, "requests.jsonl"))

    if set(expected) != set(config["caseIds"]):
        fail("expected case set differs from config")
    if len(requests) != len(config["caseIds"]) * len(config["seeds"]):
        fail("request count %d != cases*seeds" % len(requests))

    for case_id in config["caseIds"]:
        row = rows.get(case_id)
        exp = expected.get(case_id)
        if row is None or exp is None:
            fail("case missing: " + case_id)
        if "reference" in exp:
            fail("reference leaked into expected for " + case_id)
        actual_input_sha = canonical_input_sha(row["input"])
        if actual_input_sha != manifest_by_id[case_id]["inputSha256"]:
            fail("input canonical sha mismatch for " + case_id)
        if exp["inputSha256"] != actual_input_sha:
            fail("expected inputSha256 mismatch for " + case_id)
        if canonical_input_sha(exp["input"]) != actual_input_sha:
            fail("expected input bytes differ from pack for " + case_id)
        reference = (row.get("reference") or {}).get("text") or ""
        if reference:
            # The reference legitimately quotes settled input facts, so a
            # shared substring is only a leak when it is NOT in the input blob.
            input_blob = json.dumps(row["input"], ensure_ascii=False)
            prompt_texts = [entry["userPrompt"] for entry in requests if entry["caseId"] == case_id]
            for prompt in prompt_texts:
                for start in range(0, max(0, len(reference) - 16), 3):
                    chunk = reference[start:start + 16]
                    if chunk in input_blob:
                        continue
                    if chunk in prompt:
                        fail("reference-only substring leak in prompt for " + case_id)

    seen = set()
    for entry in requests:
        if entry["callId"] in seen:
            fail("duplicate callId " + entry["callId"])
        seen.add(entry["callId"])
        if entry["caseId"] not in expected:
            fail("request for unselected case " + entry["caseId"])
        if entry["seed"] not in config["seeds"]:
            fail("unexpected seed %s" % entry["seed"])
        if canonical_input_sha(rows[entry["caseId"]]["input"]) != entry["inputSha256"]:
            fail("request inputSha256 mismatch " + entry["callId"])
        if sha256_text(entry["userPrompt"]) != entry["userPromptSha256"]:
            fail("request prompt sha mismatch " + entry["callId"])
        for forbidden in ("reference", "requiredFacts", "licensedEntities"):
            if forbidden in entry["userPrompt"]:
                fail("forbidden field name %s in prompt %s" % (forbidden, entry["callId"]))

    for case_id in config["caseIds"]:
        seeds = [entry["seed"] for entry in requests if entry["caseId"] == case_id]
        if seeds != list(config["seeds"]):
            fail("seed order mismatch for " + case_id)

    print(json.dumps({
        "status": "pass",
        "batch": args.batch,
        "cases": config["caseIds"],
        "calls": len(requests),
        "checks": checks,
        "referenceLeakCheck": "no 16-char reference-only substring in any prompt",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
