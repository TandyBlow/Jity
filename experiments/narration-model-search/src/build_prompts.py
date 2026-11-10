# -*- coding: utf-8 -*-
"""Freeze the exact prompts for the narration-model comparison.

Rules this script enforces:

  * the shared development package is owned by lane 01. This script does not
    create one; it reads 01's manifest, checks the manifest sha256 the caller
    pinned, checks the cases-file sha256 that the manifest itself records, and
    checks every case's recorded `inputSha256` against the bytes on disk. A
    mismatch is a hard exit, not a warning.
  * the model input is the training-shape serialization
    (`yuyan-prose-result-v2`, same serializer the narration checkpoints were
    trained on), not an ad-hoc prompt invented here.
  * whitespace is normalised the way the browser/product path does it
    (delete space / tab / full-width space) and every removal is recorded in a
    ledger, because the reference serializer refuses to silently normalise.
  * the chat system/user wrapper is copied from lane 10's
    `chatml-instruct-v1` template (`hf-instruct.template.json`), not written
    from scratch.

Without `--provisional`, the script refuses to run when 01's rubric file is
absent or the caller has not pinned the manifest hash. `--provisional` output is
marked `frozen: false, publishable: false`; it exists to test the harness, not
to compare models.

Usage:
    python -X utf8 src/build_prompts.py \
      --manifest <01 dev-package manifest.json> \
      --cases <cases.jsonl> \
      --expect-manifest-sha256 <sha256> \
      --out-dir evidence/prompts-provisional --provisional
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
WORKTREE = ROOT.parent.parent
V2_RENDER = WORKTREE / "experiments/narration-runtime-v2/src/v2_render.py"
TEMPLATE_CONFIG = WORKTREE / "experiments/narration-runtime-v2/configs/hf-instruct.template.json"

# Frozen sampling config for the offline comparison. Greedy decode keeps the
# same input reproducible across machines; the browser arm (lane 09) is not
# bound by this and uses the product's own sampling.
SAMPLING = {
    "temperature": 0.0,
    "topK": 1,
    "topP": 1.0,
    "seed": 42,
    "maxTokens": 320,
    "contextSize": 8192,
    "stop": ["<|im_end|>", "<|endoftext|>"],
    "stream": False,
}

TEMPLATE_ID = "narration-trained-instruct-whole-scene-v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def python_json(value) -> str:
    """`json.dumps(..., ensure_ascii=False, sort_keys=True)` byte-for-byte."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def squash(value, path: str, ledger: list):
    """Delete space / tab / full-width space; record every removal."""
    if isinstance(value, str):
        removed = sum(value.count(ch) for ch in " \t\u3000")
        if removed:
            cleaned = value
            for ch in " \t\u3000":
                cleaned = cleaned.replace(ch, "")
            ledger.append({"path": path, "removed": removed, "before": value, "after": cleaned})
            return cleaned
        return value
    if isinstance(value, list):
        return [squash(item, f"{path}[{index}]", ledger) for index, item in enumerate(value)]
    if isinstance(value, dict):
        return {key: squash(item, f"{path}/{key}", ledger) for key, item in value.items()}
    return value


def load_renderer():
    if not V2_RENDER.exists():
        raise SystemExit(f"training serializer missing: {V2_RENDER}")
    sys.path.insert(0, str(V2_RENDER.parent))
    import v2_render  # noqa: E402
    return v2_render


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--cases", type=pathlib.Path, default=None,
                        help="default: manifest directory + files.cases.jsonl")
    parser.add_argument("--expect-manifest-sha256", required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--provisional", action="store_true",
                        help="allow a package without 01's RUBRIC.md; output is not frozen")
    parser.add_argument("--skip-serializer-errors", action="store_true",
                        help="provisional dry run only: record a case the reference serializer "
                             "refuses and continue; a frozen batch may never skip a case")
    parser.add_argument("--declare-subset", type=pathlib.Path, default=None,
                        help="JSON file that pre-declares the exact excluded caseIds and the "
                             "mechanical reason; required to skip a case in a pinned batch")
    args = parser.parse_args()

    manifest_bytes = args.manifest.read_bytes()
    manifest_sha = sha256_bytes(manifest_bytes)
    if manifest_sha != args.expect_manifest_sha256:
        print(f"manifest sha256 mismatch: on disk {manifest_sha}, pinned {args.expect_manifest_sha256}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    rubric = args.manifest.parent / "RUBRIC.md"
    rubric_present = rubric.exists()
    if not rubric_present and not args.provisional:
        print("01 rubric (RUBRIC.md) is absent; refusing to freeze prompts. "
              "Wait for 01's frozen package or use --provisional.", file=sys.stderr)
        return 3
    if args.skip_serializer_errors and not args.provisional and not args.declare_subset:
        print("--skip-serializer-errors requires --provisional or --declare-subset", file=sys.stderr)
        return 3
    subset = None
    if args.declare_subset:
        subset = json.loads(args.declare_subset.read_text(encoding="utf-8"))
        declared_ids = {entry["caseId"] for entry in subset.get("excludedCases", [])}
        if not declared_ids:
            print("declared subset has no excludedCases", file=sys.stderr)
            return 3

    cases_path = args.cases or (args.manifest.parent / "cases.jsonl")
    cases_bytes = cases_path.read_bytes()
    cases_sha = sha256_bytes(cases_bytes)
    recorded_cases_sha = manifest.get("files", {}).get("cases.jsonl")
    if recorded_cases_sha and cases_sha != recorded_cases_sha:
        print(f"cases sha256 mismatch: on disk {cases_sha}, manifest records {recorded_cases_sha}", file=sys.stderr)
        return 2
    cases = [json.loads(line) for line in cases_bytes.decode("utf-8").splitlines() if line.strip()]
    if manifest.get("caseCount") not in (None, len(cases)):
        print(f"case count mismatch: manifest {manifest.get('caseCount')}, file {len(cases)}", file=sys.stderr)
        return 2

    v2_render = load_renderer()
    template_config = json.loads(TEMPLATE_CONFIG.read_text(encoding="utf-8"))["template"]
    system = template_config["system"]
    prefix = template_config["userPrefix"]
    suffix = template_config["userSuffix"]

    prompts = []
    ledger_all = []
    skipped = []
    for case in cases:
        case_id = case["caseId"]
        raw_input = case["input"]
        recorded = case.get("inputSha256")
        actual = sha256_text(python_json(raw_input))
        if recorded and recorded != actual:
            print(f"{case_id}: inputSha256 mismatch: file {actual}, case says {recorded}", file=sys.stderr)
            return 2
        ledger: list = []
        normalized = squash(raw_input, "input", ledger)
        try:
            input_text = v2_render.serialize_text(normalized)
        except Exception as error:  # NarrationSerializeError carries a stable code
            detail = f"{type(error).__name__}: {error}"
            if not args.skip_serializer_errors:
                print(f"{case_id}: serializer refused the case: {detail}", file=sys.stderr)
                return 4
            if subset is not None and case_id not in declared_ids:
                print(f"{case_id}: serializer refused a case that is not in the declared subset", file=sys.stderr)
                return 2
            if subset is None and not args.provisional:
                print(f"{case_id}: serializer refused; no declared subset", file=sys.stderr)
                return 4
            skipped.append({"caseId": case_id, "error": detail})
            print(f"SKIP {case_id}: {detail}", file=sys.stderr)
            continue
        user = f"{prefix}{input_text}{suffix}"
        prompt_sha = sha256_text(system + "\n\n" + user)
        prompts.append({
            "caseId": case_id,
            "category": case.get("category"),
            "worldFamily": case.get("worldFamily"),
            "sourceRowId": (case.get("source") or {}).get("rowId"),
            "inputSha256": recorded or actual,
            "normalizedInputSha256": sha256_text(python_json(normalized)),
            "inputTextSha256": sha256_text(input_text),
            "inputChars": len(input_text),
            "system": system,
            "user": user,
            "promptSha256": prompt_sha,
            "whitespaceLedger": ledger,
            "priorTextCount": len(case.get("priorTexts") or []),
            "requiredFactCount": len(case.get("requiredFacts") or []),
        })
        ledger_all.extend({"caseId": case_id, **entry} for entry in ledger)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts_path = out_dir / "prompts.jsonl"
    tmp = prompts_path.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        for prompt in prompts:
            handle.write(json.dumps(prompt, ensure_ascii=False) + "\n")
    tmp.replace(prompts_path)
    ledger_path = out_dir / "whitespace-ledger.jsonl"
    with open(ledger_path, "w", encoding="utf-8", newline="\n") as handle:
        for entry in ledger_all:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    frozen = rubric_present and not args.provisional and (subset is not None or not skipped)
    manifest_out = {
        "templateId": TEMPLATE_ID,
        "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "frozen": frozen,
        "publishable": frozen,
        "frozenReason": None if frozen else (
            "provisional harness test: 01's RUBRIC.md is "
            + ("present but --provisional was passed" if rubric_present else "absent")
        ),
        "devPackage": {
            "owner": "01-input",
            "manifestPath": str(args.manifest),
            "manifestSha256": manifest_sha,
            "casesPath": str(cases_path),
            "casesSha256": cases_sha,
            "caseCount": len(prompts),
            "rubricPath": str(rubric) if rubric_present else None,
            "rubricSha256": sha256_bytes(rubric.read_bytes()) if rubric_present else None,
            "status": manifest.get("status"),
        },
        "serializer": {
            "version": v2_render.SERIALIZER_VERSION,
            "projectionVersion": v2_render.PROJECTION_VERSION,
            "file": str(V2_RENDER),
            "sha256": sha256_bytes(V2_RENDER.read_bytes()),
        },
        "chatTemplate": {
            "trainingConfig": str(TEMPLATE_CONFIG),
            "sha256": sha256_bytes(TEMPLATE_CONFIG.read_bytes()),
            "system": system,
            "userPrefix": prefix,
            "userSuffix": suffix,
            "application": "the model's own GGUF chat template is applied by llama-server --jinja to [system, user]",
        },
        "sampling": SAMPLING,
        "whitespaceRule": "delete space / tab / U+3000, recorded per field in whitespace-ledger.jsonl",
        "promptCount": len(prompts),
        "subset": ({
            "declared": True,
            "declaredFile": str(args.declare_subset),
            "declaredSha256": sha256_bytes(args.declare_subset.read_bytes()),
            "excludedCases": skipped,
            "note": subset.get("note"),
            "gateDenominator": f"{len(prompts)}/{len(cases)} cases; the full-pack 10/15 gate cannot be claimed from this batch",
        } if subset is not None else {"declared": False}),
        "skippedCases": skipped,
        "promptsSha256": sha256_bytes(prompts_path.read_bytes()),
        "ledgerSha256": sha256_bytes(ledger_path.read_bytes()),
        "limitations": [
            "The prompt carries the settled input only; case priorTexts are used by the checker "
            "for echo detection, not inserted into the prompt. Cross-turn context is lane 04/07's scope.",
            "The product currently wraps narrations in beat-scoped prompts (02's strategy). This frozen "
            "condition is whole-scene and is a model-comparison condition only; promotion still runs "
            "through the real product page and lane 09.",
        ],
    }
    manifest_path = out_dir / "prompts.manifest.json"
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest_out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(manifest_path)
    print(json.dumps({
        "prompts": len(prompts),
        "frozen": frozen,
        "promptsSha256": manifest_out["promptsSha256"],
        "manifestSha256": manifest_sha,
        "casesSha256": cases_sha,
        "rubricPresent": rubric_present,
        "whitespaceLedgerEntries": len(ledger_all),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
