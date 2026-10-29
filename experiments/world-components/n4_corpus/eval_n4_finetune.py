# N4 finetune dev evaluation / frozen holdout acceptance.
#
# Two modes:
# 1. corpus dev (default): two arms (base vs finetuned) judged by the SAME
#    recognizer that gates the corpus (corpus_check.check_row). Statistics
#    are per INDEPENDENT INPUT, not per row; dev inputs that also occur in
#    train are reported as REGRESSION, separately from the unseen
#    generalization denominator.
# 2. holdout (--holdout <file> --freeze <manifest>): the frozen one-shot
#    acceptance run. The freeze manifest pins the holdout, checkpoint,
#    renderer, judge, corpus and decode settings; any hash mismatch aborts
#    before inference. All inputs must be unseen except the shared atomic
#    no_change input (reported as regression, never in the unseen
#    denominator). No regeneration/fallback; one greedy decode.
#
# The committed r1 archive was produced on the earlier 52-row corpus (4 dev
# rows) and is pinned by its corpus hashes; use a run tag (e.g.
# `--run-tag r2-small`) for a new corpus so the r1 archive is not
# overwritten (the script aborts on an r1/hash mismatch).
#
# Decode: the single DECODE dict (greedy, max_new_tokens=64, num_beams=1,
# tokenizer legacy=False) is used by the freeze check, the tokenizer, the
# generate() call and the report — there is no second copy of these values.
# No quality verdicts beyond the recognizer's three states; the coordinator
# decides the overall gate.
#
# Usage: python experiments/world-components/n4_corpus/eval_n4_finetune.py [--run-tag r2-small]
#        python experiments/world-components/n4_corpus/eval_n4_finetune.py \
#          --run-tag r3-direction \
#          --holdout experiments/world-components/n4_holdout/holdout.jsonl \
#          --freeze experiments/world-components/n4_holdout/freeze-r3-direction.json \
#          [--verify-only]
# --holdout and --freeze must be given together; --verify-only without
# both exits before any model import instead of falling into the dev
# inference path.
# Output: artifacts/world-components/n4-finetune-eval-<tag>.json (corpus)
#         artifacts/world-components/n4-holdout-eval-<tag>.json (holdout)

import hashlib
import importlib.machinery
import json
import pathlib
import sys
import time
import types


# ---- argument parsing and entry guards (round 16 review #2) ----------------
# Parsed before torch/transformers are imported, so a missing flag exits
# immediately instead of silently falling into the corpus-dev inference path.
def arg_value(flag: str, default):
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv) or sys.argv[i + 1].startswith("--"):
        sys.exit(f"{flag} requires a value")
    return sys.argv[i + 1]


RUN_TAG = arg_value("--run-tag", "r1")
HOLDOUT = arg_value("--holdout", None)
FREEZE = arg_value("--freeze", None)
VERIFY_ONLY = "--verify-only" in sys.argv
if bool(HOLDOUT) != bool(FREEZE):
    missing = "--freeze" if HOLDOUT else "--holdout"
    sys.exit(f"{missing} is required together with "
             f"{'--holdout' if HOLDOUT else '--freeze'}; refusing to infer")
if VERIFY_ONLY and not HOLDOUT:
    sys.exit("--verify-only requires BOTH --holdout and --freeze; "
             "refusing to fall into the corpus-dev inference path")

try:
    import pyarrow  # noqa: F401
except Exception:
    stub = types.ModuleType("pyarrow")
    stub.__version__ = "16.1.0"
    stub.__path__ = []
    sys.modules["pyarrow"] = stub
tf_stub = types.ModuleType("tensorflow")
tf_stub.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
tf_stub.__path__ = []
sys.modules.setdefault("tensorflow", tf_stub)

import torch  # noqa: E402
import transformers  # noqa: E402
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration  # noqa: E402
from transformers.models.t5.tokenization_t5 import T5Tokenizer  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from n4_render import render_input, corpus_hashes  # noqa: E402
import corpus_check  # noqa: E402

REPO = HERE.parent.parent.parent
BASE_MODEL = HERE.parent / "assets" / "randeng-t5-77m"
FINETUNED = HERE.parent / "assets" / "n4-finetune" / RUN_TAG
if HOLDOUT:
    REPORT = REPO / "artifacts" / "world-components" / f"n4-holdout-eval-{RUN_TAG}.json"
else:
    REPORT = REPO / "artifacts" / "world-components" / f"n4-finetune-eval-{RUN_TAG}.json"

if RUN_TAG == "r1" and REPORT.exists():
    pinned = json.loads(REPORT.read_text(encoding="utf-8"))
    recorded = pinned["provenance"]["corpusAndRenderer"]["corpus.seeds.jsonl"]
    if recorded != corpus_hashes()["corpus.seeds.jsonl"]:
        sys.exit("r1 archive is pinned to the earlier corpus; "
                 "pass --run-tag r2-small for the expanded corpus")
# SINGLE source of truth for decoding (round 16 review #1): the freeze
# verification compares THIS dict with the frozen manifest, and the
# tokenizer setting, generate() call and report all READ THIS DICT. There is
# no second copy, so editing a "different" constant can no longer pass the
# freeze check while changing inference.
DECODE = {"greedy": True, "maxNewTokens": 64, "numBeams": 1,
          "tokenizerLegacy": False}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_hashes(path: pathlib.Path) -> dict:
    return {f.name: sha_file(f)[:16] for f in sorted(path.iterdir()) if f.is_file()}


def plan_key(plan: list) -> str:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True)


def load_corpus_rows() -> list:
    rows = []
    for f in (HERE / "corpus.seeds.jsonl", HERE / "rewrites.jsonl"):
        rows += [json.loads(line) for line in
                 f.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


def atomic_no_change(row: dict) -> bool:
    return bool(row["plan"]) and all(e["kind"] == "no_change" for e in row["plan"])


def merge_units(rows: list, seen_inputs: set) -> list:
    """One independent evaluation unit per distinct rendered input. All rows
    sharing an input must carry the same plan (asserted), because greedy
    decoding produces one output for that prompt."""
    by_input = {}
    for r in rows:
        by_input.setdefault(render_input(r["plan"]), []).append(r)
    units = []
    for key, members in by_input.items():
        if len({plan_key(m["plan"]) for m in members}) != 1:
            print(f"MERGE ERROR: one rendered input maps to different plans: {key!r}")
            sys.exit(2)
        rep = members[0]
        groups = sorted({m["sourceGroupId"] for m in members})
        units.append({
            "input": key,
            "row": rep,
            "devGroups": groups,
            "rowsMerged": len(members),
            "rowOrigins": sorted({m["rowOrigin"] for m in members}),
            "seenInTrain": key in seen_inputs,
            "trainGroups": [],
        })
    units.sort(key=lambda u: (u["seenInTrain"], u["devGroups"][0]))
    return units


def load_dev_inputs():
    rows = load_corpus_rows()
    problems = corpus_check.split_isolation_problems(rows, 120, 30)
    if problems:
        for p in problems:
            print("ISOLATION:", p)
        sys.exit(2)
    train_groups_by_input = {}
    for r in rows:
        if r["split"] == "train":
            key = render_input(r["plan"])
            train_groups_by_input.setdefault(key, set()).add(r["sourceGroupId"])
    units = merge_units([r for r in rows if r["split"] == "dev"],
                        set(train_groups_by_input))
    for u in units:
        u["trainGroups"] = sorted(train_groups_by_input.get(u["input"], []))
    return rows, units


def load_holdout_inputs(path: pathlib.Path, corpus_rows: list) -> list:
    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or any(r.get("split") != "holdout" for r in rows):
        sys.exit(f"holdout file must contain only split=holdout rows: {path}")
    seen_inputs = {render_input(r["plan"]) for r in corpus_rows}
    units = merge_units(rows, seen_inputs)
    hard = [u for u in units if u["seenInTrain"] and not atomic_no_change(u["row"])]
    if hard:
        for u in hard:
            print("HOLDOUT INPUT SEEN IN CORPUS:", u["devGroups"])
        sys.exit(f"holdout shares {len(hard)} non-atomic input(s) with the corpus")
    return units


def freeze_problems(m: dict, holdout_path: pathlib.Path) -> list:
    """Every pinned artifact plus the runtime decode configuration is
    compared against the manifest. Round 15 review: trainingReport and the
    holdout authority report were pinned but never checked, and the runtime
    decode settings were not compared with the frozen ones at all."""
    problems = []
    checks = {
        "renderer": (sha_file(HERE / "n4_render.py"), m["renderer"]["sha256"]),
        "judge": (sha_file(HERE / "corpus_check.py"), m["judge"]["sha256"]),
        "holdout": (sha_file(holdout_path), m["holdout"]["sha256"]),
        "holdout.authorityReport": (
            sha_file(pathlib.Path(m["holdout"]["authorityReport"]["file"])),
            m["holdout"]["authorityReport"]["sha256"]),
        "corpus.seeds.jsonl": (sha_file(HERE / "corpus.seeds.jsonl"),
                               m["corpus"]["corpus.seeds.jsonl"]),
        "rewrites.jsonl": (sha_file(HERE / "rewrites.jsonl"),
                           m["corpus"]["rewrites.jsonl"]),
        "trainingReport": (sha_file(pathlib.Path(m["trainingReport"]["file"])),
                           m["trainingReport"]["sha256"]),
        "checkpoint": (dir_hashes(FINETUNED), m["checkpoint"]["sha256_16"]),
        "baseModel": (dir_hashes(BASE_MODEL), m["baseModel"]["sha256_16"]),
    }
    for k, (cur, want) in checks.items():
        if cur != want:
            problems.append(f"FREEZE MISMATCH {k}: current={cur} frozen={want}")
    if m.get("decode") != DECODE:
        problems.append(f"FREEZE MISMATCH decode: runtime={DECODE} "
                        f"frozen={m.get('decode')}")
    return problems


def freeze_selftest(m: dict, holdout_path: pathlib.Path) -> list:
    """Tamper self-test (round 15): every pinned field must be caught when
    its recorded value is altered, and the untouched manifest must pass.
    Runs in memory on a copy; the real manifest file is never written."""
    import copy
    void = []
    if freeze_problems(m, holdout_path):
        void.append("clean manifest does not verify")
    tampers = [
        ("renderer", lambda d: d["renderer"].__setitem__("sha256", "0" * 64)),
        ("judge", lambda d: d["judge"].__setitem__("sha256", "0" * 64)),
        ("holdout", lambda d: d["holdout"].__setitem__("sha256", "0" * 64)),
        ("holdout.authorityReport",
         lambda d: d["holdout"]["authorityReport"].__setitem__("sha256", "0" * 64)),
        ("corpus.seeds.jsonl",
         lambda d: d["corpus"].__setitem__("corpus.seeds.jsonl", "0" * 64)),
        ("rewrites.jsonl",
         lambda d: d["corpus"].__setitem__("rewrites.jsonl", "0" * 64)),
        ("trainingReport",
         lambda d: d["trainingReport"].__setitem__("sha256", "0" * 64)),
        ("checkpoint",
         lambda d: d["checkpoint"].__setitem__("sha256_16", {"model.safetensors": "0" * 16})),
        ("baseModel",
         lambda d: d["baseModel"].__setitem__("sha256_16", {"config.json": "0" * 16})),
        ("decode.maxNewTokens", lambda d: d["decode"].__setitem__("maxNewTokens", 1)),
        ("decode.greedy", lambda d: d["decode"].__setitem__("greedy", False)),
        ("decode.numBeams", lambda d: d["decode"].__setitem__("numBeams", 4)),
        ("decode.tokenizerLegacy",
         lambda d: d["decode"].__setitem__("tokenizerLegacy", True)),
    ]
    for label, mutate in tampers:
        tampered = copy.deepcopy(m)
        mutate(tampered)
        if not freeze_problems(tampered, holdout_path):
            void.append(f"freeze self-test {label}: tamper NOT caught")
    return void


def verify_freeze(manifest_path: pathlib.Path, holdout_path: pathlib.Path):
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    # 1. the supplied manifest must match the files on disk (a tampered
    #    manifest is rejected here, before the self-test can mask it)
    problems = freeze_problems(m, holdout_path)
    if problems:
        for x in problems:
            print(x)
        sys.exit(2)
    # 2. the checks themselves must be able to catch tampering
    void = freeze_selftest(m, holdout_path)
    if void:
        print("REPORT VOID — freeze self-test failed:")
        for x in void:
            print(" ", x)
        sys.exit(2)
    print(f"freeze self-test PASS: 13/13 tampers caught (trainingReport, "
          f"holdout authority report and decode config included)")
    return m


def judge(dev_row: dict, text: str) -> dict:
    """Run the corpus recognizer over a generated text as if it were the
    row's narration; hashes are recomputed so only the recognition verdict
    matters here. planRefs are NOT inherited from the dev row: the row's
    refs encode ITS sentence organization, while the model may organize the
    same plan differently (legally) — refs are re-expanded to the generated
    sentence count so the verdict rests on expression evidence and residue,
    not on matching one row's layout."""
    row = json.loads(json.dumps(dev_row, ensure_ascii=False))
    row["text"] = text
    sentences = [s for s in text.split("。") if s.strip()]
    all_refs = [e["ref"] for e in row["plan"]]
    row["planRefs"] = [all_refs for _ in sentences]
    row["mustExpress"] = list(all_refs)
    row["hashes"]["text"] = sha(text)
    fails, reviews = corpus_check.check_row(row)
    verdict = "fail" if fails else ("review" if reviews else "pass")
    return {"verdict": verdict, "fails": fails, "reviews": reviews}


def summarize(results: list) -> dict:
    counts = {"pass": 0, "review": 0, "fail": 0}
    for x in results:
        counts[x["verdict"]] += 1
    n = len(results) or 1
    return {"inputs": len(results), "verdicts": counts,
            "meanWall": round(sum(x["wallSeconds"] for x in results) / n, 2),
            "meanTokens": round(sum(x["outputTokens"] for x in results) / n, 1)}


def run_arms(units: list, tokenizer) -> dict:
    arms = {}
    for arm, path in (("base", BASE_MODEL), ("finetuned", FINETUNED)):
        model = T5ForConditionalGeneration.from_pretrained(str(path), torch_dtype=torch.float32)
        model.cuda()  # v7 correction: the model must be on the eval device
        model.eval()
        results = {"unseen": [], "regression": []}
        for u in units:
            section = "regression" if u["seenInTrain"] else "unseen"
            prompt = u["input"]
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            t0 = time.perf_counter()
            with torch.no_grad():
                out = model.generate(**inputs,
                                     max_new_tokens=DECODE["maxNewTokens"],
                                     num_beams=DECODE["numBeams"],
                                     do_sample=not DECODE["greedy"])
            wall = round(time.perf_counter() - t0, 2)
            text = tokenizer.decode(out[0], skip_special_tokens=True)
            verdict = judge(u["row"], text)
            results[section].append({
                "devGroups": u["devGroups"], "rowOrigin": u["rowOrigins"],
                "rowsMerged": u["rowsMerged"],
                "seenInTrain": u["seenInTrain"],
                "trainGroups": u["trainGroups"],
                "input": prompt, "output": text, "outputTokens": int(out.shape[1]),
                "wallSeconds": wall, **verdict,
            })
            print(f"[{arm}][{section}] {u['devGroups'][0]} ({u['rowsMerged']} row(s)) "
                  f"{wall}s -> {verdict['verdict']}: {text[:60]}")
        arms[arm] = {"unseen": summarize(results["unseen"]),
                     "regression": summarize(results["regression"]),
                     "results": results}
        del model
    return arms


def write_verify_only(freeze: dict, units: list) -> None:
    """--verify-only: prove the frozen pieces and the tamper self-test hold
    WITHOUT running inference (used for engineering sign-off, round 15)."""
    unseen = [u for u in units if not u["seenInTrain"]]
    regression = [u for u in units if u["seenInTrain"]]
    out = {
        "purpose": f"freeze verification only ({RUN_TAG}); no model inference",
        "mode": "freeze-verify",
        "freeze": {"file": FREEZE, "sha256": sha_file(pathlib.Path(FREEZE))},
        "checks": {
            "pinnedArtifacts": ["renderer", "judge", "holdout",
                                "holdout.authorityReport",
                                "corpus.seeds.jsonl", "rewrites.jsonl",
                                "trainingReport", "checkpoint", "baseModel"],
            "decode": dict(DECODE),
            "decodeComparedToFrozen": True,
            "tokenizer": {"legacy": DECODE["tokenizerLegacy"],
                          "note": "reported from DECODE, the same dict the "
                                  "tokenizer and generate() read"},
            "tamperSelftest": "13/13 caught",
        },
        "holdout": {"file": HOLDOUT, "sha256": sha_file(pathlib.Path(HOLDOUT)),
                    "rows": sum(u["rowsMerged"] for u in units),
                    "distinctInputs": len(units),
                    "unseenInputs": len(unseen),
                    "sharedRegressionInputs": len(regression)},
        "note": "engineering closure only; the acceptance numbers stay in "
                "n4-holdout-eval-r3-direction.json (no re-run performed)",
    }
    path = REPO / "artifacts" / "world-components" / f"n4-holdout-freeze-verify-{RUN_TAG}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"verify-only report -> {path}")


def main() -> None:
    corpus_rows = load_corpus_rows()
    freeze = None
    if HOLDOUT:
        if not FREEZE:
            sys.exit("holdout mode requires --freeze <manifest>")
        freeze = verify_freeze(pathlib.Path(FREEZE), pathlib.Path(HOLDOUT))
        units = load_holdout_inputs(pathlib.Path(HOLDOUT), corpus_rows)
        if VERIFY_ONLY:
            write_verify_only(freeze, units)
            return
        unseen = [u for u in units if not u["seenInTrain"]]
        regression = [u for u in units if u["seenInTrain"]]
        dev_rows = sum(u["rowsMerged"] for u in units)
        print(f"holdout rows: {dev_rows} -> independent inputs: {len(units)} "
              f"(unseen {len(unseen)}, shared regression {len(regression)})")
    else:
        rows, units = load_dev_inputs()
        unseen = [u for u in units if not u["seenInTrain"]]
        regression = [u for u in units if u["seenInTrain"]]
        dev_rows = sum(u["rowsMerged"] for u in units)
        print(f"dev rows: {dev_rows} -> independent inputs: {len(units)} "
              f"(unseen {len(unseen)}, regression {len(regression)})")
    for u in regression:
        print(f"  regression input ({u['devGroups']}): "
              f"{u['input'].replace(chr(10), '|')[:80]}")

    tokenizer = T5Tokenizer(vocab_file=str(BASE_MODEL / "spiece.model"),
                            legacy=DECODE["tokenizerLegacy"])
    arms = run_arms(units, tokenizer)

    report = {
        "purpose": (f"n4 holdout acceptance {RUN_TAG} (frozen setup; coordinator decides the gate)"
                    if HOLDOUT else
                    f"n4 finetune dev eval {RUN_TAG} (per-input; quality accepted separately)"),
        "mode": "holdout" if HOLDOUT else "corpus-dev",
        "provenance": {"corpusAndRenderer": corpus_hashes(),
                       "baseModel": dir_hashes(BASE_MODEL),
                       "finetuned": dir_hashes(FINETUNED)},
        "environment": {"python": sys.version.split()[0], "torch": torch.__version__,
                        "transformers": transformers.__version__,
                        "device": "cuda",
                        "deviceName": torch.cuda.get_device_name(0)},
        "decode": dict(DECODE),
        "tokenizer": {"legacy": DECODE["tokenizerLegacy"],
                      "note": "same pin as training and the zero-shot baseline"},
        "judge": "corpus_check.check_row over the row's own plan/refs/must "
                 "(hashes recomputed for the generated text; planRefs re-expanded "
                 "to the generated sentence count)",
        "arms": arms,
    }
    if HOLDOUT:
        report["freeze"] = {"file": str(FREEZE), "sha256": sha_file(FREEZE)}
        report["holdout"] = {
            "file": str(HOLDOUT),
            "sha256": sha_file(HOLDOUT),
            "rows": dev_rows,
            "distinctInputs": len(units),
            "unseenInputs": len(unseen),
            "sharedRegressionInputs": len(regression),
            "sharedRegression": [
                {"input": u["input"], "rows": u["rowsMerged"],
                 "sourceGroups": u["devGroups"]} for u in regression],
            "freezeRule": freeze["acceptanceRule"],
        }
        u = arms["finetuned"]["unseen"]
        passed = u["inputs"] > 0 and u["verdicts"]["pass"] == u["inputs"]
        report["acceptance"] = {
            "rule": freeze["acceptanceRule"],
            "unseenInputs": len(unseen),
            "pass": u["verdicts"]["pass"], "review": u["verdicts"]["review"],
            "fail": u["verdicts"]["fail"],
            "result": "met" if passed else "not-met",
            "note": "automatic result under the frozen per-input criterion; the "
                    "overall quality gate remains the coordinator's decision",
        }
    else:
        report["isolation"] = {
            "check": "corpus_check.split_isolation_problems(120 train groups, 30 dev groups)",
            "result": "pass"}
        report["devInputs"] = {
            "devRows": dev_rows,
            "uniqueInputs": len(units),
            "unseenInputs": len(unseen),
            "regressionInputs": len(regression),
            "regressionDetail": [
                {"input": u["input"], "devGroups": u["devGroups"],
                 "trainGroups": u["trainGroups"], "rowsMerged": u["rowsMerged"]}
                for u in regression],
            "mergeRule": "one generation per distinct rendered input; rows sharing "
                         "an input share the plan and greedy output (seed/rewrite, "
                         "expressed/omitted duplicates, frozen duplicates). Seen "
                         "inputs are excluded from the unseen denominator.",
        }
        report["devGroups"] = sorted({r["sourceGroupId"] for r in rows
                                      if r["split"] == "dev"})
        report["disclaimers"] = [
            "unseen-input denominator only; regression inputs are reported "
            "separately and never counted as generalization",
            "quality gate closure needs broader coverage and human review",
            "Chinese naturalness is left to human review at delivery acceptance",
            "training saw the plan rendering; zero-shot base did not",
        ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
