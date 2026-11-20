# -*- coding: utf-8 -*-
"""Turn a corrected semantic-case pack into the frozen prompt format screen.py runs.

Lane 11's semantic probe uses the *production* system/user prompts supplied by
03/04 after their reference/coverage fixes. This script only freezes those
strings into the same JSONL/manifest shape as the narration batch, so the HPC
runner and the validator stay separate from the prose quality gate.

Pack JSONL needs: caseId, system, user, optional maxTokens, optional input.
`--frozen` is an explicit act: it must not be passed while the prompts still
contain a known placeholder/coverage defect.

Usage:
    python -X utf8 src/prepare_semantic_prompts.py --pack semantic-probes/pack.jsonl \
        --out-dir evidence/semantic-prompts-v1 --frozen
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SAMPLING = {
    "temperature": 0.0,
    "topK": 1,
    "topP": 1.0,
    "seed": 42,
    "maxTokens": 520,
    "contextSize": 8192,
    "stop": [],
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=pathlib.Path, required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--frozen", action="store_true")
    parser.add_argument("--sampling", type=pathlib.Path,
                        help="JSON file overriding temperature/topK/topP/seed/maxTokens/contextSize/stop")
    args = parser.parse_args()

    raw = args.pack.read_text(encoding="utf-8")
    pack_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not rows:
        print("empty pack", file=sys.stderr)
        return 2
    if args.frozen:
        bad = [row.get("caseId") for row in rows
               if row.get("correctedContract") is not True or not row.get("contractCommit")]
        if bad:
            print(f"refusing to freeze: cases missing correctedContract=true/contractCommit: {bad}",
                  file=sys.stderr)
            return 2
    sampling = dict(DEFAULT_SAMPLING)
    if args.sampling:
        sampling.update(json.loads(args.sampling.read_text(encoding="utf-8")))

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    prompts = []
    for index, row in enumerate(rows):
        case_id = row.get("caseId")
        system = row.get("system")
        user = row.get("user")
        if not case_id or not isinstance(system, str) or not isinstance(user, str):
            print(f"case {index}: missing caseId/system/user", file=sys.stderr)
            return 2
        prompt = {
            "caseId": case_id,
            "system": system,
            "user": user,
            "inputSha256": sha256_text(json.dumps(row.get("input"), ensure_ascii=False, sort_keys=True))
            if "input" in row else None,
            "promptSha256": sha256_text(system + "\x00" + user),
        }
        if row.get("maxTokens") is not None:
            prompt["maxTokens"] = int(row["maxTokens"])
        prompts.append(prompt)
    (out / "prompts.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in prompts) + "\n",
        encoding="utf-8", newline="\n")
    manifest = {
        "kind": "structured-semantic-prompts",
        "frozen": bool(args.frozen),
        "frozenAt": datetime.datetime.now(datetime.timezone.utc).isoformat() if args.frozen else None,
        "pack": str(args.pack),
        "packSha256": pack_sha,
        "contractCommits": sorted({row.get("contractCommit") for row in rows if row.get("contractCommit")}),
        "promptCount": len(prompts),
        "sampling": sampling,
        "note": "system/user are the corrected 03/04 production prompts; this is a structural "
                "capability probe, not the narration quality gate",
    }
    (out / "prompts.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "prompts": len(prompts), "frozen": manifest["frozen"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
