"""Build the frozen input manifest for the greedy vs beam-2 comparison (v1).

What it reads (read-only, no model loading):
  * the three weight-side files of the local u240 copy
  * every input set named in comparison-protocol-v1.md §3, with file hash,
    unit/source/kind counts, template features (does the rendered input carry a
    要求 block / a 方向 line?) and a per-unit sha256 of the rendered input
  * the three u240 training pools, for the overlap rule
  * the judging scripts that already exist in either tree
  * the protocol document itself

What it writes:
  experiments/world-components/parallel/fact_wording/freeze/comparison-inputs-v1.json

It does not run inference and does not write outside this task's directory.

Usage:
    python -X utf8 build_comparison_manifest.py           # write the manifest
    python -X utf8 build_comparison_manifest.py --print   # and print a table
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]      # .../parallel/fact_wording
TREE_C4 = HERE.parents[5]        # this worktree root
REPO = HERE.parents[8]           # <repo>
NEXT = REPO / ".local/world-components-next-worktree"
WC = REPO / ".local/world-components-worktree"
OUT = EXPERIMENT / "freeze"

U240_FILES = {
    "model.safetensors": REPO / ".local/models/u240-model.safetensors",
    "config.json": REPO / ".local/models/config.json",
    "spiece.model": REPO / ".local/models/spiece.model",
}

VERSION = "v1"
if "--version" in sys.argv:
    VERSION = sys.argv[sys.argv.index("--version") + 1]
PROTOCOL = EXPERIMENT / {
    "v3": "comparison-protocol-v3.md",
    "v2": "comparison-protocol-v2.md",
}.get(VERSION, "comparison-protocol-v1.md")

TREES = {"c4": TREE_C4, "next": NEXT, "wc": WC}

# role: diagnostic | candidate | acceptance
INPUT_SETS = [
    dict(id="cf24", role="diagnostic", tree="c4", primary=True,
         path="artifacts/world-components/n4-cf24-contract.jsonl",
         note="第一轮主集；u240 输出已存在（cf24-u240-baseline），属旧题"),
    dict(id="final24", role="diagnostic", tree="next", primary=False,
         path="artifacts/next-inputs/world-components/n4-final24-contract.jsonl",
         note="u240 输出已存在（target-revision-r1/val-u240），不盲；只能追加诊断"),
    dict(id="moved24", role="diagnostic", tree="next", primary=False,
         path="artifacts/next-inputs/world-components/n4-moved24-contract.jsonl",
         note="移动单类补充；同世界，非独立"),
    dict(id="syntax-gap-probes", role="diagnostic", tree="next", primary=False,
         path="artifacts/next-acceptance/syntax-gap-r1/n4-probe-r1.jsonl",
         note="由 cf24 错误派生的最小对照探针；u240 输出已存在"),
    dict(id="decode-compare-90", role="diagnostic", tree="wc", primary=False,
         path="artifacts/decode-compare/cases.json",
         note="旧回归输入；JSON 容器，单元在 cases[] 里"),
    dict(id="decode-compare-215", role="diagnostic", tree="wc", primary=False,
         path="artifacts/decode-compare/diag215-cases.json",
         note="旧诊断输入；JSON 容器"),
    dict(id="decode-compare-40", role="diagnostic", tree="wc", primary=False,
         path="artifacts/decode-compare/confirm40.json",
         note="旧确认输入；短模板（无“要求”段），不能与 cf24 模板混表"),
]

TRAINING_POOLS = [
    dict(name="verbalizer", tree="c4",
         path="experiments/world-components/n4_narrative_dev/verbalizer_pairs.jsonl",
         lines=229),
    dict(name="expand-train80", tree="next",
         path="artifacts/next-inputs/world-components/n4-expand-train80.jsonl",
         lines=80),
    dict(name="object-train40", tree="next",
         path="artifacts/next-inputs/world-components/n4-object-train40.jsonl",
         lines=40),
]

JUDGE_SCRIPTS = [
    dict(tree="c4", path="experiments/world-components/n4_narrative_dev/fact_contract.py", role="fact-field contract check"),
    dict(tree="c4", path="experiments/world-components/n4_narrative_dev/judge_expression.py", role="expression judge used by earlier N4 rounds"),
    dict(tree="c4", path="experiments/world-components/n4_narrative_dev/n4_pipeline.py", role="reference pipeline (input rendering)"),
    dict(tree="next", path="experiments/world-components/run_cf24_baseline.py", role="runner that produced the u240 cf24 baseline"),
    dict(tree="next", path="experiments/world-components/score_cf24_baseline.py", role="mechanical S/O/C/A scorer"),
    dict(tree="next", path="experiments/world-components/review_cf24_baseline.py", role="review helper used for the 24-source human pass"),
    dict(tree="next", path="experiments/world-components/check_cf24_overlap.py", role="training-overlap checker"),
]

# Overlap results already computed by earlier rounds (not recomputed here).
RECORDED_OVERLAP = {
    "cf24": dict(
        source="artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-baseline/cf24-overlap.json",
        sourceSha256Prefix="51dedce5047c4f13",
        units=85, independent=74, seen=11,
        criterion="independent = neither the rendered input nor the fact signature occurs in a training pool",
        caveat="pools named only (verbalizer_pairs / expand-train80 / object-train40); no file hash in that record",
    ),
    "final24": dict(
        source="artifacts/validation-freeze-r1/freeze.json",
        units=76, independent=43,
        criterion="signature = kind + subject + value, or kind + subject + from + to; matched against the three hashed pools and cf24",
        caveat="computed for the later arm question; must be re-verified against the three pools pinned in comparison-protocol-v1.md §3.2",
    ),
}

REQUIRED_ENV = dict(python="3.12.3", torch="2.7.0+cu126", transformers="4.57.3",
                    device="cpu", dtype="float32", threads=4)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_commit(path: Path) -> str | None:
    root = path
    while root != root.parent and not (root / ".git").exists():
        root = root.parent
    try:
        out = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or None
    except Exception:
        return None


def load_units(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    doc = json.loads(text)
    return doc["cases"] if isinstance(doc, dict) and "cases" in doc else doc


def unit_id(unit: dict) -> str:
    return unit.get("unitId") or unit.get("caseId") or "?"


def source_id(unit: dict):
    """The sets name their origin differently: sourceId / source / roundId."""
    return unit.get("sourceId") or unit.get("source") or unit.get("roundId")


def input_hash(unit: dict) -> str:
    raw = unit.get("input", "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def template_features(units: list[dict]) -> dict:
    with_req = sum(1 for u in units if "要求：" in u.get("input", ""))
    with_dir = sum(1 for u in units if "\n方向=" in u.get("input", ""))
    moved = sum(1 for u in units if u.get("kind") == "moved")
    return dict(unitsWithRequirementBlock=with_req, unitsWithDirectionLine=with_dir,
                movedUnits=moved,
                mixedTemplate=0 < with_req < len(units))


def current_env() -> dict:
    out = dict(python=None, torch=None, transformers=None, sentencepiece=None)
    import sys
    out["python"] = sys.version.split()[0]
    for name in ("torch", "transformers", "sentencepiece"):
        if importlib.util.find_spec(name) is not None:
            try:
                mod = __import__(name)
                out[name] = getattr(mod, "__version__", "installed")
            except Exception as exc:  # broken install
                out[name] = f"broken: {type(exc).__name__}"
        else:
            out[name] = None
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    weight = {}
    for name, path in U240_FILES.items():
        weight[name] = dict(path=str(path).replace("\\", "/"),
                            bytes=path.stat().st_size, sha256=sha256(path))

    input_sets = []
    per_unit = {}
    for spec in INPUT_SETS:
        path = TREES[spec["tree"]] / spec["path"]
        row = dict(id=spec["id"], role=spec["role"], primary=spec["primary"],
                   tree=spec["tree"], path=str(path.relative_to(REPO)).replace("\\", "/"),
                   note=spec["note"], exists=path.exists())
        if path.exists():
            units = load_units(path)
            row.update(
                bytes=path.stat().st_size, sha256=sha256(path),
                units=len(units),
                sources=len({source_id(u) for u in units}),
                kinds=dict(sorted(Counter(u.get("kind") for u in units).items())),
                template=template_features(units),
            )
            hashes = {unit_id(u): input_hash(u) for u in units}
            row["duplicateInputs"] = len(hashes) != len(units)
            per_unit[spec["id"]] = hashes
        row["recordedOverlap"] = RECORDED_OVERLAP.get(spec["id"])
        # Every set below already has u240 output archived somewhere, so none of
        # them can be treated as a blind acceptance set.
        row["blindToU240"] = False
        row["u240OutputArchive"] = {
            "cf24": "artifacts/next-acceptance/cf24-u240-baseline/",
            "final24": "artifacts/next-acceptance/target-revision-r1/val-u240/",
            "moved24": None,
            "syntax-gap-probes": "artifacts/next-acceptance/syntax-gap-r1/probe-u240/",
        }.get(spec["id"], "unknown (old decode-compare outputs exist but carry no checkpoint identity)")
        input_sets.append(row)

    pools = []
    for spec in TRAINING_POOLS:
        path = TREES[spec["tree"]] / spec["path"]
        entry = dict(name=spec["name"], tree=spec["tree"],
                     path=str(path.relative_to(REPO)).replace("\\", "/"),
                     declaredLines=spec["lines"], exists=path.exists())
        if path.exists():
            entry.update(bytes=path.stat().st_size, sha256=sha256(path),
                         lines=sum(1 for line in path.open(encoding="utf-8") if line.strip()))
        pools.append(entry)

    judges = []
    for spec in JUDGE_SCRIPTS:
        path = TREES[spec["tree"]] / spec["path"]
        judges.append(dict(tree=spec["tree"], role=spec["role"],
                           path=str(path.relative_to(REPO)).replace("\\", "/"),
                           exists=path.exists(),
                           sha256=sha256(path) if path.exists() else None))

    protocol_sha = sha256(PROTOCOL) if PROTOCOL.exists() else None

    extras = {}
    if VERSION in ("v2", "v3"):
        def digest(rel: str):
            """Paths are relative to this task's directory, recorded relative to the tree root."""
            path = EXPERIMENT / rel
            shown = str(path.relative_to(TREE_C4)).replace(chr(92), "/")
            return dict(path=shown, exists=path.exists(),
                        sha256=sha256(path) if path.exists() else None)

        extras = dict(
            protocolDocuments=(
                dict(current=digest("comparison-protocol-v3.md"),
                     older=[digest("comparison-protocol-v2.md"), digest("comparison-protocol-v1.md")],
                     rule="v3 replaces v2 §2.3/§2.5/§3/§5 (rounded strict stop, unified 64-token cap, run records); v1/v2 kept unchanged")
                if VERSION == "v3" else
                dict(current=digest("comparison-protocol-v2.md"),
                     superseded=digest("comparison-protocol-v1.md"),
                     rule="v2 replaces v1 §1.4 and §6 P7; v1 stays on disk unchanged")),
            beam2=dict(
                implementation=digest("scripts/beam2.py"),
                tests=digest("scripts/preflight_beam2.py"),
                p7Result=digest("artifacts/fact-wording/preflight/p7-beam2.json"),
                spec="width 2, expand 2, no length normalisation, EOS scored, sound stop rule, total order (-round(score,6), len, tokens, beam index), 64-token cap",
            ),
            runner=digest("scripts/run_preflight.py"),
            diagnosticRunner=digest("scripts/run_diagnostic.py"),
            blindPack=digest("scripts/build_blind_pack.py"),
            environmentRecords=dict(
                lock=digest("env/requirements.lock.txt"),
                notes=digest("env/ENVIRONMENT.md"),
                interpreter="env/Scripts/python.exe",
            ),
            upstreamScripts=dict(
                provenance=digest("scripts/upstream/provenance.json"),
                direction="read-only copies; originals untouched; local changes must be new files",
            ),
            crossCheck=None,  # filled below with the archived u240 cf24 baseline
        )

    manifest = dict(
        protocol=f"comparison-inputs-{VERSION}",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        generated_by=dict(
            script=str(HERE.relative_to(TREE_C4)).replace("\\", "/"),
            scriptSha256=sha256(HERE),
        ),
        protocolDoc=dict(path=str(PROTOCOL.relative_to(TREE_C4)).replace("\\", "/"),
                         sha256=protocol_sha),
        trees={name: dict(path=str(p).replace("\\", "/"), commit=tree_commit(p))
               for name, p in TREES.items()},
        weight=weight,
        device=dict(device=REQUIRED_ENV["device"], dtype=REQUIRED_ENV["dtype"],
                    threads=REQUIRED_ENV["threads"],
                    batch=1,
                    note="CPU fp32 4 threads to match the cf24 u240 baseline; GPU runs need a separate table"),
        environment=dict(required=REQUIRED_ENV, current=current_env()),
        decode=dict(
            greedy=dict(policy="argmax per step; stop at EOS; no length cap; 20 s wall clock per unit"),
            beam2=dict(width=2, expandPerBeam=2, candidatesPerStep=4,
                       lengthNormalization="none (raw cumulative log-probability)",
                       stop="2 finished hypotheses, or take best finished on budget",
                       tieBreak="earlier finished first, then ascending token id",
                       budgetSeconds=20.0,
                       note="new implementation; the old 305-case beam script is lost, so B is not a reproduction of it"),
            timeout=dict(budgetSeconds=20.0, retryOnInfraError=1,
                         fallback="none: no template/rule/other-arm substitution",
                         timeoutVerdict="U (undetermined, never counted as pass)"),
        ),
        inputSets=input_sets,
        perUnitInputSha256=per_unit,
        trainingPools=pools,
        judgeScripts=judges,
        acceptanceSlot=dict(
            registered=False,
            schema=["unitId", "source", "fact", "entityId/fieldPath", "input+inputSha256", "overlap"],
            rule="missing any field -> unit excluded; overlap -> regression only; no source -> excluded",
            status="empty: no independent set has been registered; cf24/final24/moved24/probes all have u240 output archived already",
        ),
        unmetConditions=[
            dict(id="env", blocking=True,
                 item="python/torch/transformers/sentencepiece",
                 detail="current interpreter lacks torch, transformers and sentencepiece; cf24 baseline used python 3.12.3, torch 2.7.0+cu126, transformers 4.57.3",
                 unblock="install or point to a matching environment and record its versions; otherwise label results as not strictly comparable"),
            dict(id="runner", blocking=True,
                 item="run/score/review/overlap scripts absent from this tree",
                 detail="the four cf24 scripts exist only in .local/world-components-next-worktree; judgeScripts lists their hashes",
                 unblock="copy them read-only into this task's directory, re-hash, and pin the copies"),
            dict(id="beam2-impl", blocking=True,
                 item="no beam-2 implementation exists",
                 detail="the old beam script is lost and beam-cache-equivalence.json shows two past implementations disagreed (max score gap 72.127905)",
                 unblock="write the implementation from comparison-protocol-v1.md §1.4, pass preflight P6/P7, then freeze its hash"),
            dict(id="acceptance-set", blocking=False,
                 item="independent acceptance set not registered",
                 detail="6 mandatory fields per unit are empty; all current sets are old-question diagnostics",
                 unblock="fill the §3.2 registration table and run the overlap check against the three pinned pools"),
            dict(id="pool-provenance", blocking=False,
                 item="u240 training pools pinned by hash now, not at training time",
                 detail="no training-time input hash record exists; overlap verdicts are 'against these pinned pools', not 'against what u240 actually saw'",
                 unblock="state the limitation in every overlap claim; do not claim provable independence"),
            dict(id="gpu-parity", blocking=False,
                 item="CPU only",
                 detail="no GPU run of these exact comparison arms; GPU token-identical output unverified",
                 unblock="run a labelled second table on GPU and report both"),
            dict(id="second-reviewer", blocking=False,
                 item="single human reviewer",
                 detail="no second reviewer for the blind verdicts",
                 unblock="record the limitation, or add a second reviewer for a ≤10-unit batch"),
            dict(id="old-beam-reproduction", blocking=False,
                 item="old 305-case beam cannot be reproduced",
                 detail="algorithm details (length norm, candidate count, tie-break) were never recorded",
                 unblock="treat the old table as non-comparable; do not rank new B against it"),
        ],
        preflight=[
            dict(id="P1", check="weight sha256 equals the frozen value"),
            dict(id="P2", check="config.json and spiece.model sha256 equal the frozen values"),
            dict(id="P3", check="input file hash, unit count and every per-unit inputSha256 match this manifest"),
            dict(id="P4", check="judge script hashes match this manifest"),
            dict(id="P5", check="greedy twice on t01:f0, t07:f0, t11:f1, t22:f0, t24:f1 gives identical text"),
            dict(id="P6", check="beam-2 twice on the same five units gives identical text"),
            dict(id="P7", check="beam-2 unit test on a synthetic distribution matches the frozen spec"),
            dict(id="P8", check="both arms report the same inputSha256 for every unit"),
            dict(id="P9", check="environment versions match the frozen values, else label as not strictly comparable"),
        ],
    )

    if extras:
        archive = NEXT / "artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-baseline/cf24-baseline.json"
        extras["crossCheck"] = dict(
            purpose="compare the preflight greedy text of the 5 units with the archived u240 cf24 output",
            path=str(archive.relative_to(REPO)).replace(chr(92), "/"),
            exists=archive.exists(),
            sha256=sha256(archive) if archive.exists() else None,
            evidence="artifacts/fact-wording/preflight/preflight.json -> x1",
        )
        manifest.update(extras)
    (OUT / f"comparison-inputs-{VERSION}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if "--print" in sys.argv:
        print("protocol sha256:", protocol_sha)
        print("weight         :", weight["model.safetensors"]["sha256"])
        print("\ninput sets:")
        for row in input_sets:
            print(f"  {row['id']:<22} units={row.get('units','-'):<4} sources={row.get('sources','-'):<4} "
                  f"{row.get('sha256','-')[:16]}  role={row['role']}  blind={row['blindToU240']}")
            if row.get("template"):
                print(f"      template: {row['template']}")
        print("\ntraining pools:")
        for pool in pools:
            print(f"  {pool['name']:<16} lines={pool.get('lines','-'):<4} declared={pool['declaredLines']:<4} {pool.get('sha256','-')[:16]}")
        print("\njudge scripts:")
        for j in judges:
            print(f"  {j['tree']:<5} {'ok ' if j['exists'] else 'MISSING'} {str(j['sha256'])[:16]:<18} {j['path']}")
        print("\nunmet:", [u["id"] for u in manifest["unmetConditions"] if u["blocking"]], "(blocking)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
