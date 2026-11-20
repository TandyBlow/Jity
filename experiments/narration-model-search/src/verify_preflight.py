# -*- coding: utf-8 -*-
"""Verify one downloaded model against the pinned lane-11 expectations.

This is the mechanical acceptance check for lane 10's preflight. It does not
load weights or generate text; it hashes the file, reads its GGUF metadata and
(optionally) checks that a saved smoke response contains non-empty text.

Usage:
    python -X utf8 src/verify_preflight.py --model-id qwen35-2b \
        --path /scratch/models/Qwen3.5-2B-Q4_K_M.gguf \
        --smoke-json /scratch/models/qwen35-2b.smoke.json

If lane 10 uses a different file name, the expectations still come from
models/candidates.json. Exit 0 = pass, 2 = mismatch or unreadable model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
CANDIDATES = ROOT / "models/candidates.json"
sys.path.insert(0, str(HERE))
from gguf_probe import read_gguf  # noqa: E402


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def smoke_text(path: pathlib.Path) -> tuple[bool, str]:
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return False, f"smoke json unreadable: {type(error).__name__}: {error}"
    choices = body.get("choices") or []
    if not choices:
        return False, "smoke response has no choices"
    message = choices[0].get("message") or {}
    text = message.get("content") or choices[0].get("text") or ""
    if not str(text).strip():
        return False, "smoke response text is empty"
    return True, f"smoke text {len(str(text))} chars"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", help="candidate id; supplies expectations")
    parser.add_argument("--path", type=pathlib.Path, required=True)
    parser.add_argument("--expect-sha256")
    parser.add_argument("--expect-arch")
    parser.add_argument("--expect-template-sha256")
    parser.add_argument("--smoke-json", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()

    expected = {}
    if args.model_id:
        registry = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        expected = next((row for row in registry["candidates"] if row["id"] == args.model_id), {})
        if not expected:
            print(f"unknown candidate id: {args.model_id}", file=sys.stderr)
            return 2
    expect_sha = args.expect_sha256 or (expected.get("gguf") or {}).get("lfsSha256")
    expect_arch = args.expect_arch or (expected.get("operatorEvidence") or {}).get("expectedArchitecture")
    expect_template = (args.expect_template_sha256
                       or (expected.get("operatorEvidence") or {}).get("chatTemplateSha256"))
    expect_bytes = (expected.get("gguf") or {}).get("bytes")

    reasons = []
    if not args.path.exists():
        print(f"missing file: {args.path}", file=sys.stderr)
        return 2
    if expect_bytes is not None and args.path.stat().st_size != expect_bytes:
        reasons.append(f"size {args.path.stat().st_size} != expected {expect_bytes}")
    actual_sha = sha256_file(args.path)
    if expect_sha and actual_sha.lower() != expect_sha.lower():
        reasons.append(f"sha256 {actual_sha[:16]}... != expected {expect_sha[:16]}...")

    probe = {}
    try:
        report = read_gguf(args.path)
        probe = report["summary"]
    except Exception as error:  # noqa: BLE001 - a malformed GGUF is a real failure
        reasons.append(f"GGUF probe failed: {type(error).__name__}: {error}")

    actual_arch = probe.get("architecture")
    if expect_arch and actual_arch != expect_arch:
        reasons.append(f"architecture {actual_arch!r} != expected {expect_arch!r}")
    actual_template = probe.get("chatTemplateSha256")
    if expect_template and actual_template != expect_template:
        reasons.append(f"chat template {str(actual_template)[:16]}... != expected {expect_template[:16]}...")

    smoke = None
    if args.smoke_json:
        ok, detail = smoke_text(args.smoke_json)
        smoke = {"path": str(args.smoke_json), "ok": ok, "detail": detail}
        if not ok:
            reasons.append(detail)

    result = {
        "modelId": args.model_id,
        "path": str(args.path),
        "bytes": args.path.stat().st_size,
        "sha256": actual_sha,
        "architecture": actual_arch,
        "quantization": probe.get("quantization"),
        "chatTemplateSha256": actual_template,
        "expected": {"sha256": expect_sha, "architecture": expect_arch,
                     "chatTemplateSha256": expect_template, "bytes": expect_bytes},
        "smoke": smoke,
        "ok": not reasons,
        "reasons": reasons,
        "note": "hash + GGUF metadata + optional saved smoke response; this is not a quality judgement",
    }
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
