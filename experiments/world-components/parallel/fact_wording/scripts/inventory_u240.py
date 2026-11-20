"""Read-only inventory of the frozen u240 checkpoint and the evidence usable for c4.

What this script does, in order:

1. Reads the three weight-side files of the local u240 copy
   (`.local/models/u240-model.safetensors`, `config.json`, `spiece.model`),
   plus the duplicate `model.safetensors`, and computes size + sha256.
2. Reads every file listed as an "identity declaration" and counts how often the
   computed weight/config/tokenizer hashes appear there, so a claim like
   "byte-identical to ~/n4uni/ckpt-u240" is tied to an actual record.
3. Reads every evidence file listed below, computes size + sha256, and pulls out
   whatever checkpoint identity the file itself records
   (`model.files.model.safetensors`, `modelSha256`, `base.modelSha256`, ...).
   An evidence file with no recorded identity is marked `identity-missing`.
4. Cross-checks the decode-compare hashes against the 16-char prefixes printed in
   `design/world-engine-reports/components/candidate-selection-space-v1.md` §8.
5. Writes `freeze/u240-identity-v1.json` and `freeze/evidence-inventory-v1.json`.

Nothing outside this task's own directory is written; every other tree is opened
read-only. No model is loaded and no generation is run.

Usage:
    python -X utf8 inventory_u240.py           # write the two JSON files
    python -X utf8 inventory_u240.py --print   # also print a summary table
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]          # .../parallel/fact_wording
TREE_C4 = HERE.parents[5]            # this task's own worktree root
REPO = HERE.parents[8]               # <repo>
OUT = EXPERIMENT / "freeze"

U240_LOCAL = REPO / ".local/models/u240-model.safetensors"
U240_DUPLICATE = REPO / ".local/models/model.safetensors"
U240_CONFIG = REPO / ".local/models/config.json"
U240_TOKENIZER = REPO / ".local/models/spiece.model"

NEXT = REPO / ".local/world-components-next-worktree"
WC = REPO / ".local/world-components-worktree"

# Files that make a claim about what u240 is. The script does not trust the
# claim: it only records it and counts occurrences of the hashes it computed.
IDENTITY_DECLARATIONS = [
    NEXT / "design/world-engine-reports/components/three-arm-plan-2026-11-05.md",
    NEXT / "design/world-engine-reports/components/cf24-baseline-2026-11-05.md",
    NEXT / "design/world-engine-reports/components/eval-r1-2026-11-05.md",
    NEXT / "artifacts/three-arm-r1/three-arm-freeze.json",
    NEXT / "artifacts/next-acceptance/cf24-u240-baseline/index.json",
    NEXT / "artifacts/next-acceptance/target-revision-r1/index.json",
]

# Evidence: model outputs or data sets. `identity_from` names the JSON keys the
# file may use to identify its checkpoint; the script checks each in order.
EVIDENCE = [
    # --- indexes that own the run-level checkpoint identity ---------------
    dict(id="target-revision.index", kind="index", tree="next",
         path="artifacts/next-acceptance/target-revision-r1/index.json",
         purpose="two-arm continuation from u240; its `base.modelSha256` names u240",
         identity_from=["base.modelSha256"]),
    dict(id="syntax-gap.index", kind="index", tree="next",
         path="artifacts/next-acceptance/syntax-gap-r1/index.json",
         purpose="remaining-error inventory and minimal-contrast probes; its `model` block names u240",
         identity_from=["model.modelSha256", "u240.modelSha256"]),
    # --- output produced by the frozen u240 itself -------------------------
    dict(id="cf24-u240-baseline.index", kind="index", tree="next",
         path="artifacts/next-acceptance/cf24-u240-baseline/index.json",
         purpose="cf24 quality baseline run on u240 (raw output, mechanical verdicts, overlap, human review, edit-layer variant)",
         identity_from=["modelSha256"]),
    dict(id="cf24-u240-baseline.raw", kind="model-output", tree="next", owner="cf24-u240-baseline.index",
         path="artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-baseline/cf24-baseline.json",
         purpose="greedy output for 85 cf24 units on u240 (CPU)",
         identity_from=[]),
    dict(id="cf24-u240-baseline.mechanical", kind="score", tree="next", owner="cf24-u240-baseline.index",
         path="artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-baseline/cf24-mechanical.json",
         purpose="mechanical S/O/C/A verdicts on the u240 cf24 output",
         identity_from=[]),
    dict(id="cf24-u240-baseline.overlap", kind="diagnostic", tree="next", owner="cf24-u240-baseline.index",
         path="artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-baseline/cf24-overlap.json",
         purpose="training-set overlap of the 85 cf24 units (fact signature level)",
         identity_from=[]),
    dict(id="cf24-u240-baseline.review", kind="human-review", tree="next", owner="cf24-u240-baseline.index",
         path="artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-baseline/cf24-review.json",
         purpose="per-source human review of the u240 cf24 output (the only per-item human labels for u240)",
         identity_from=[]),
    dict(id="cf24-moved-rule.raw", kind="model-output", tree="next", owner="cf24-u240-baseline.index",
         path="artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-moved-rule/cf24-baseline.json",
         purpose="u240 second run with the added input sentence for the 10 moved units (input fix that failed)",
         identity_from=[]),
    dict(id="val-u240.raw", kind="model-output", tree="next", owner="target-revision.index",
         path="artifacts/next-acceptance/target-revision-r1/val-u240/val-baseline.json",
         purpose="u240 greedy output on the final24 validation set",
         identity_from=["model.files.model.safetensors"]),
    dict(id="val-u240.mechanical", kind="score", tree="next", owner="target-revision.index",
         path="artifacts/next-acceptance/target-revision-r1/val-u240/cf24-mechanical-val-baseline.json",
         purpose="mechanical verdicts on the u240 final24 output",
         identity_from=[]),
    dict(id="syntax-gap.probe-u240", kind="model-output", tree="next", owner="syntax-gap.index",
         path="artifacts/next-acceptance/syntax-gap-r1/probe-u240/probe-baseline.json",
         purpose="u240 output on the frozen minimal-contrast syntax probes (GPU)",
         identity_from=["model.files.model.safetensors"]),
    dict(id="syntax-gap.review", kind="human-review", tree="next", owner="syntax-gap.index",
         path="artifacts/next-acceptance/syntax-gap-r1/review-r1.json",
         purpose="review covering the u240 and c syntax-gap probes; the file itself records no checkpoint hash",
         identity_from=[]),

    # --- output whose checkpoint identity was never recorded --------------
    dict(id="decode-compare.arm-ab", kind="model-output", tree="wc",
         path="artifacts/decode-compare/arm-ab.json",
         purpose="greedy vs beam-2 on the 90-case regression set",
         identity_from=[]),
    dict(id="decode-compare.diag215-ab", kind="model-output", tree="wc",
         path="artifacts/decode-compare/diag215-ab.json",
         purpose="greedy vs beam-2 on the 215-case diagnostic set",
         identity_from=[]),
    dict(id="decode-compare.confirm40-ab", kind="model-output", tree="wc",
         path="artifacts/decode-compare/confirm40-ab.json",
         purpose="greedy vs beam-2 on the 40-case confirmation set",
         identity_from=[]),
    dict(id="decode-compare.cases", kind="input-set", tree="wc",
         path="artifacts/decode-compare/cases.json",
         purpose="the 90 frozen decode cases with their inputs and input hashes",
         identity_from=[]),
    dict(id="decode-compare.diag215-cases", kind="input-set", tree="wc",
         path="artifacts/decode-compare/diag215-cases.json",
         purpose="the 215 diagnostic-case inputs",
         identity_from=[]),
    dict(id="decode-compare.confirm40-cases", kind="input-set", tree="wc",
         path="artifacts/decode-compare/confirm40-cases.json",
         purpose="the 40 confirmation-case inputs",
         identity_from=[]),
    dict(id="decode-beam-review", kind="human-review", tree="wc",
         path="artifacts/world-components/decode-beam-review-v1.md",
         purpose="item-by-item review of the 32 cases where greedy and beam differ",
         identity_from=[]),

    # --- input sets available to c4 ---------------------------------------
    dict(id="cf24-contract", kind="input-set", tree="c4",
         path="artifacts/world-components/n4-cf24-contract.jsonl",
         purpose="the 85 single-fact units / 24 sources of the cf24 evaluation set",
         identity_from=[]),
    dict(id="cf24-scoring-v2", kind="score", tree="next",
         path="artifacts/next-inputs/world-components/n4-cf24-scoring-v2.json",
         purpose="older per-fact cf24 verdicts for base/arm1/arm2/422/431 (no u240 arm, no checkpoint hash)",
         identity_from=[]),
]

DECODE_DOC = TREE_C4 / "design/world-engine-reports/components/candidate-selection-space-v1.md"
CF24_DOC = NEXT / "design/world-engine-reports/components/cf24-baseline-2026-11-05.md"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safetensors_shape(path: Path) -> dict:
    """Read the safetensors header only: tensor count, parameter count, dtypes."""
    import struct
    with path.open("rb") as fh:
        header_len = struct.unpack("<Q", fh.read(8))[0]
        header = json.loads(fh.read(header_len))
    tensors = {k: v for k, v in header.items() if k != "__metadata__"}
    params = 0
    for info in tensors.values():
        count = 1
        for dim in info["shape"]:
            count *= dim
        params += count
    return dict(tensors=len(tensors), params=params,
                dtypes=sorted({info["dtype"] for info in tensors.values()}),
                metadata=header.get("__metadata__"))


def tree_commit(path: Path) -> str | None:
    root = path
    while root != root.parent and not (root / ".git").exists():
        root = root.parent
    if root == root.parent:
        return None
    try:
        out = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def dig(obj, key: str):
    """Look up `key`, preferring the literal key over a dotted path.

    Some archives store file names as keys, e.g. {"model": {"files":
    {"model.safetensors": "<sha>"}}}; splitting that on dots would miss it.
    """
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        head, sep, rest = key.partition(".")
        if sep and head in obj:
            return dig(obj[head], rest)
    return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    local_hash = sha256(U240_LOCAL)
    config_hash = sha256(U240_CONFIG)
    tokenizer_hash = sha256(U240_TOKENIZER)

    weights = []
    for label, path in [
        ("u240 (canonical local copy)", U240_LOCAL),
        ("duplicate of the same bytes", U240_DUPLICATE),
        ("config", U240_CONFIG),
        ("tokenizer", U240_TOKENIZER),
    ]:
        weights.append(dict(
            label=label, path=str(path.relative_to(REPO)).replace("\\", "/"),
            bytes=path.stat().st_size, sha256=sha256(path),
        ))

    declarations = []
    for path in IDENTITY_DECLARATIONS:
        if not path.exists():
            declarations.append(dict(path=str(path.relative_to(REPO)).replace("\\", "/"),
                                     exists=False))
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        declarations.append(dict(
            path=str(path.relative_to(REPO)).replace("\\", "/"),
            exists=True,
            bytes=path.stat().st_size,
            sha256=sha256(path),
            mentions_weight_sha256=text.count(local_hash),
            mentions_weight_prefix8=text.count(local_hash[:8]),
            mentions_config_sha256=text.count(config_hash),
            mentions_config_prefix8=text.count(config_hash[:8]),
            mentions_tokenizer_sha256=text.count(tokenizer_hash),
            mentions_tokenizer_prefix8=text.count(tokenizer_hash[:8]),
            mentions_u240=text.count("u240"),
        ))

    evidence = []
    index_declared = {}
    for entry in EVIDENCE:
        base = {"next": NEXT, "wc": WC, "c4": TREE_C4}[entry["tree"]]
        path = base / entry["path"]
        row = dict(
            id=entry["id"], kind=entry["kind"], purpose=entry["purpose"],
            tree=entry["tree"],
            path=str(path.relative_to(REPO)).replace("\\", "/"),
            exists=path.exists(),
        )
        if path.exists():
            row["bytes"] = path.stat().st_size
            row["sha256"] = sha256(path)
            declared = None
            if path.suffix == ".json":
                try:
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    for key in entry["identity_from"]:
                        value = dig(doc, key)
                        if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
                            declared = value
                            break
                except Exception:
                    pass
            if declared:
                row["declared_model_sha256"] = declared
                row["identity"] = "u240-confirmed" if declared == local_hash else "other-checkpoint"
            else:
                row["identity"] = "identity-missing"
        evidence.append(row)

    # A run-level index can carry the identity for the files it lists.
    by_id = {row["id"]: row for row in evidence}
    for row in evidence:
        owner_id = next((e.get("owner") for e in EVIDENCE if e["id"] == row["id"]), None)
        if not owner_id:
            continue
        owner = by_id.get(owner_id) or {}
        row["identity_owner"] = owner.get("path")
        row["identity_owner_status"] = owner.get("identity")
        if row["identity"] == "identity-missing" and owner.get("identity") == "u240-confirmed":
            row["identity"] = "u240-confirmed"

    # Input sets are data, not model output: they carry no checkpoint on purpose.
    for row in evidence:
        if row["kind"] == "input-set" and row["identity"] == "identity-missing":
            row["identity"] = "not-applicable (input set)"
    by_id["cf24-scoring-v2"]["note"] = (
        "per-fact cf24 verdicts for arms base/arm1/arm2/422/431; no u240 arm and no checkpoint hash, "
        "so it cannot be compared with the u240 numbers")

    # cf24 baseline index self-declares a sha256 for each of its files
    cf24_index_path = NEXT / "artifacts/next-acceptance/cf24-u240-baseline/index.json"
    index_checks = []
    if cf24_index_path.exists():
        idx = json.loads(cf24_index_path.read_text(encoding="utf-8"))
        for item in idx.get("files", []):
            target = NEXT / item["path"]
            actual = sha256(target) if target.exists() else None
            index_checks.append(dict(
                path=item["path"], declared=item["sha256"], actual=actual,
                matches=actual == item["sha256"],
            ))
        index_declared["cf24-u240-baseline"] = dict(
            modelSha256=idx.get("modelSha256"),
            model_matches_local=idx.get("modelSha256") == local_hash,
            unitFileSha256=idx.get("unitFileSha256"),
            files=index_checks,
        )

    # decode-compare: the review doc prints 16-char prefixes of each file hash
    prefix_checks = []
    if DECODE_DOC.exists():
        text = DECODE_DOC.read_text(encoding="utf-8")
        for name, prefix in re.findall(
                r"\|\s*`artifacts/decode-compare/([^`]+)`\s*\|[^|]*\|\s*`([0-9a-f]{16})…`\s*\|", text):
            target = WC / "artifacts/decode-compare" / name
            actual = sha256(target) if target.exists() else None
            prefix_checks.append(dict(
                path=f"artifacts/decode-compare/{name}", declared_prefix=prefix,
                actual_prefix=actual[:16] if actual else None,
                matches=bool(actual) and actual.startswith(prefix),
            ))

    cf24_contract_check = None
    if CF24_DOC.exists():
        m = re.search(r"n4-cf24-contract\.jsonl`（sha `([0-9a-f]{8,64})…`）", CF24_DOC.read_text(encoding="utf-8"))
        contract = TREE_C4 / "artifacts/world-components/n4-cf24-contract.jsonl"
        if m and contract.exists():
            actual = sha256(contract)
            cf24_contract_check = dict(
                path="artifacts/world-components/n4-cf24-contract.jsonl",
                declared_prefix=m.group(1), actual=actual,
                matches=actual.startswith(m.group(1)),
                units=sum(1 for _ in contract.open(encoding="utf-8")),
            )

    if cf24_contract_check:
        for row in evidence:
            if row["id"] == "cf24-contract":
                row["declared_prefix"] = cf24_contract_check["declared_prefix"]
                row["declared_matches"] = cf24_contract_check["matches"]
                row["units"] = cf24_contract_check["units"]

    identity = dict(
        protocol="c4-u240-identity-v1",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        written_by="experiments/world-components/parallel/fact_wording/scripts/inventory_u240.py",
        u240={
            "arch": "T5ForConditionalGeneration, d_model 512, 8 layers, 8 heads, d_ff 1024",
            "safetensors": safetensors_shape(U240_LOCAL),
            "weight_sha256": local_hash,
            "weight_bytes": U240_LOCAL.stat().st_size,
            "config_sha256": config_hash,
            "tokenizer_sha256": tokenizer_hash,
            "local_path": str(U240_LOCAL).replace("\\", "/"),
            "duplicate_path": str(U240_DUPLICATE).replace("\\", "/"),
            "duplicate_identical": sha256(U240_DUPLICATE) == local_hash,
        },
        weights=weights,
        declarations=declarations,
        trees={name: dict(path=str(p).replace("\\", "/"), commit=tree_commit(p))
               for name, p in [("c4", TREE_C4), ("next", NEXT), ("wc", WC)]},
    )

    identity["verdicts"] = dict(
        weight_identity=[
            "the two local files (u240-model.safetensors, model.safetensors) are byte-identical",
            "three archives/records declare this exact sha256 for u240: three-arm-freeze.json, "
            "cf24-u240-baseline/index.json, target-revision-r1/index.json (base)",
            "the HPC copy ~/n4uni/ckpt-u240 is only recorded as 'byte-identical' in three-arm-plan-2026-11-05.md; "
            "no hash of the HPC file was recomputed here",
        ],
        config_tokenizer=[
            "config.json and spiece.model are pinned by prefix (cd553527, c65feffa) in three-arm-plan-2026-11-05.md",
            "spiece.model equals the 784M run tokenizer byte-for-byte per sentence-base-784m-plan-v1.md",
        ],
        blocked=[
            "decode-compare greedy/beam archives: no checkpoint identity in the files or the scripts; "
            "candidate-selection-space-v1.md already refuses to call them u240 results",
            "no training log or commit-bound record ties this checkpoint to a specific code revision; "
            "identity rests on hash agreement across the four records above",
        ],
    )

    inventory = dict(
        protocol="c4-evidence-inventory-v1",
        generated_at=identity["generated_at"],
        written_by=identity["written_by"],
        rules=[
            "an evidence file counts as u240 evidence only if it, or the index that owns it, records the weight sha256 above",
            "files with no recorded checkpoint identify a process, not u240; they are kept for diagnostics only",
            "sha256 is recomputed here, never copied from a report",
        ],
        evidence=evidence,
        index_declarations=index_declared,
        decode_prefix_checks=prefix_checks,
        cf24_contract_check=cf24_contract_check,
    )

    (OUT / "u240-identity-v1.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "evidence-inventory-v1.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if "--print" in sys.argv:
        print("u240 weight sha256 :", local_hash)
        print("u240 weight bytes  :", f"{U240_LOCAL.stat().st_size:,}")
        print("duplicate identical:", identity["u240"]["duplicate_identical"])
        print("\ndeclarations:")
        for d in declarations:
            if d.get("exists"):
                print(f"  {d['path']}\n    weight full={d['mentions_weight_sha256']} prefix8={d['mentions_weight_prefix8']} "
                      f"config full={d['mentions_config_sha256']} prefix8={d['mentions_config_prefix8']} "
                      f"tokenizer full={d['mentions_tokenizer_sha256']} prefix8={d['mentions_tokenizer_prefix8']}")
        print("\nevidence:")
        for e in evidence:
            print(f"  {e['id']:<28} {e.get('identity', 'missing-file'):<20} {e.get('sha256', '-')[:16]}  {e['path']}")
        print("\ncf24 index file checks:", len(index_checks),
              "all match:", all(c["matches"] for c in index_checks))
        print("decode prefix checks:", len(prefix_checks),
              "all match:", all(c["matches"] for c in prefix_checks))
        print("cf24 contract:", cf24_contract_check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
