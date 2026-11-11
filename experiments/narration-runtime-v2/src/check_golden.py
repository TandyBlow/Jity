# -*- coding: utf-8 -*-
"""Recompute every golden vector and compare it with the recorded expectation."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import v2_render as v2


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def check_ok(case: Dict[str, Any], problems: List[str]) -> None:
    projection = case["projection"]
    expected = case["expected"]
    serialized = v2.serialize(projection)
    text = serialized.text
    data = text.encode("utf-8")
    if text != expected["text"]:
        problems.append(f"{case['caseId']}: text differs")
    if hashlib.sha256(data).hexdigest() != expected["sha256"]:
        problems.append(f"{case['caseId']}: sha256 differs")
    if data.hex() != expected["bytesUtf8Hex"]:
        problems.append(f"{case['caseId']}: hex bytes differ")
    if text.encode("utf-8").hex() != expected["bytesUtf8Hex"]:
        problems.append(f"{case['caseId']}: hex is not the UTF-8 of text")
    actual_segments = [segment.as_dict() for segment in serialized.segments]
    if actual_segments != expected["segments"]:
        problems.append(f"{case['caseId']}: segments differ")
    for segment in expected["segments"]:
        start, end = segment["charStart"], segment["charEnd"]
        if not (0 <= start <= end <= len(text)):
            problems.append(f"{case['caseId']}: segment out of range {segment}")
            continue
        if not text[start:end]:
            problems.append(f"{case['caseId']}: empty segment {segment}")
        if segment["field"] == "entity" and text[start:end] != segment["entity"]:
            problems.append(f"{case['caseId']}: entity segment mismatch {segment}")
    if any(char in "\r\n" or char.isspace() for char in text):
        problems.append(f"{case['caseId']}: serialized text contains whitespace")


def check_error(case: Dict[str, Any], problems: List[str]) -> None:
    expected = case["expected"]
    stage = expected["stage"]
    if stage == "normalize":
        import projection_v2 as projection
        try:
            projection.normalize_projection(case.get("rawProjection", case["projection"]))
        except v2.NarrationSerializeError as error:
            if error.code != expected["errorCode"]:
                problems.append(f"{case['caseId']}: normalize code {error.code} != "
                                f"{expected['errorCode']}")
            return
        problems.append(f"{case['caseId']}: expected normalize error {expected['errorCode']}")
        return
    if stage in ("build", "serialize"):
        try:
            projection = case["projection"]
            if stage == "build":
                result, _ = v2.build_result(projection["上回合状态"],
                                            projection["本回合变化"],
                                            projection["本回合状态"])
                projection = dict(projection)
                projection["本回合状态"] = result
            v2.serialize(projection)
        except v2.NarrationSerializeError as error:
            if error.code != expected["errorCode"]:
                problems.append(f"{case['caseId']}: {stage} code {error.code} != "
                                f"{expected['errorCode']}")
            return
        problems.append(f"{case['caseId']}: expected {stage} error {expected['errorCode']}")
        return
    if stage == "tokenizer":
        # The projection is already normalized and serializable; the tokenizer
        # check is a separate stage.  Re-run it against the YuYan profile.
        from tokenizer_profile import load_tokenizer_profile, validate_tokenizer_text
        profile = load_tokenizer_profile(os.path.join(ROOT, "tokenizers", "yuyan-v1",
                                                      "dict.txt"))
        serialized = v2.serialize(case["projection"])
        try:
            validate_tokenizer_text(serialized.text, profile)
        except v2.NarrationSerializeError as error:
            if error.code != expected["errorCode"]:
                problems.append(f"{case['caseId']}: tokenizer code {error.code} != "
                                f"{expected['errorCode']}")
            return
        problems.append(f"{case['caseId']}: expected tokenizer error {expected['errorCode']}")
        return
    problems.append(f"{case['caseId']}: unknown stage {stage}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=os.path.join(ROOT, "golden", "vectors.jsonl"))
    args = parser.parse_args()
    cases = read_jsonl(args.golden)
    problems: List[str] = []
    for case in cases:
        if case["expected"]["status"] == "ok":
            check_ok(case, problems)
        else:
            check_error(case, problems)
    summary = {"ok": not problems, "cases": len(cases), "problems": problems}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
