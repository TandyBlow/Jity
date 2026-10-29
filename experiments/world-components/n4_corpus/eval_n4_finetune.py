# N4 finetune dev evaluation: two arms (base vs finetuned), judged by the
# SAME recognizer that gates the corpus (corpus_check.check_row) — a
# generation counts as faithful only when the plan's mustExpress entries are
# recognized with value-consistent parses.
#
# Round 12 (review requirement): statistics are per INDEPENDENT INPUT, not
# per row. Rows that share one rendered input (seed+rewrite, two time
# plans of one source group, duplicated frozen groups) produce the same
# greedy output from the same prompt, so they are merged to one evaluation
# unit before generation. Dev inputs that also occur in train are reported
# as REGRESSION, separately from the unseen generalization denominator;
# frozen base collisions stay visible but never inflate the unseen count.
#
# The committed r1 archive was produced on the earlier 52-row corpus (4 dev
# rows) and is pinned by its corpus hashes; the current corpus has 120 dev
# rows / 56 distinct inputs. Use a run tag (e.g. `--run-tag r2-small`) for a
# new corpus so the r1 archive is not overwritten (the script aborts on an
# r1/hash mismatch).
#
# Decode: greedy, max_new_tokens=64, tokenizer legacy=False (same pin as
# training and the zero-shot baseline). No quality verdicts beyond the
# recognizer's three states; human review of the generated texts happens at
# delivery acceptance.
#
# Usage: python experiments/world-components/n4_corpus/eval_n4_finetune.py [--run-tag r2-small]
# Output: artifacts/world-components/n4-finetune-eval-<tag>.json

import hashlib
import importlib.machinery
import json
import pathlib
import sys
import time
import types

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
RUN_TAG = (sys.argv[sys.argv.index("--run-tag") + 1]
           if "--run-tag" in sys.argv else "r1")
FINETUNED = HERE.parent / "assets" / "n4-finetune" / RUN_TAG
REPORT = REPO / "artifacts" / "world-components" / f"n4-finetune-eval-{RUN_TAG}.json"

if RUN_TAG == "r1" and REPORT.exists():
    pinned = json.loads(REPORT.read_text(encoding="utf-8"))
    recorded = pinned["provenance"]["corpusAndRenderer"]["corpus.seeds.jsonl"]
    if recorded != corpus_hashes()["corpus.seeds.jsonl"]:
        sys.exit("r1 archive is pinned to the earlier corpus; "
                 "pass --run-tag r2-small for the expanded corpus")
MAX_NEW = 64


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_key(plan: list) -> str:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True)


def load_dev_inputs():
    """Load both splits; merge dev rows by rendered input (one independent
    evaluation unit per distinct prompt) and split the units into unseen vs
    seen-in-train (regression)."""
    rows = []
    for f in (HERE / "corpus.seeds.jsonl", HERE / "rewrites.jsonl"):
        rows += [json.loads(line) for line in
                 f.read_text(encoding="utf-8").splitlines() if line.strip()]
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

    by_input = {}
    for r in rows:
        if r["split"] == "dev":
            by_input.setdefault(render_input(r["plan"]), []).append(r)

    units = []
    for key, members in by_input.items():
        if len({plan_key(m["plan"]) for m in members}) != 1:
            print(f"MERGE ERROR: one rendered input maps to different plans: {key!r}")
            sys.exit(2)
        rep = members[0]
        dev_groups = sorted({m["sourceGroupId"] for m in members})
        units.append({
            "input": key,
            "row": rep,
            "devGroups": dev_groups,
            "rowsMerged": len(members),
            "rowOrigins": sorted({m["rowOrigin"] for m in members}),
            "seenInTrain": key in train_groups_by_input,
            "trainGroups": sorted(train_groups_by_input.get(key, [])),
        })
    units.sort(key=lambda u: (u["seenInTrain"], u["devGroups"][0]))
    return rows, units


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


def main() -> None:
    rows, units = load_dev_inputs()
    unseen = [u for u in units if not u["seenInTrain"]]
    regression = [u for u in units if u["seenInTrain"]]
    dev_rows = sum(u["rowsMerged"] for u in units)
    print(f"dev rows: {dev_rows} -> independent inputs: {len(units)} "
          f"(unseen {len(unseen)}, regression {len(regression)})")
    for u in regression:
        print(f"  regression input ({u['devGroups']} <- train {u['trainGroups']}): "
              f"{u['input'].replace(chr(10), '|')[:80]}")

    tokenizer = T5Tokenizer(vocab_file=str(BASE_MODEL / "spiece.model"), legacy=False)

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
                out = model.generate(**inputs, max_new_tokens=MAX_NEW,
                                     num_beams=1, do_sample=False)
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

    report = {
        "purpose": f"n4 finetune dev eval {RUN_TAG} (per-input; quality accepted separately)",
        "provenance": {"corpusAndRenderer": corpus_hashes(),
                       "baseModel": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:16]
                                     for f in sorted(BASE_MODEL.iterdir()) if f.is_file()},
                       "finetuned": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:16]
                                     for f in sorted(FINETUNED.iterdir()) if f.is_file()}},
        "environment": {"python": sys.version.split()[0], "torch": torch.__version__,
                        "transformers": transformers.__version__,
                        "device": "cuda",
                        "deviceName": torch.cuda.get_device_name(0),
                        "note": "v7 correction: r1's eval actually ran on CPU because "
                                "the model was never moved; reports now record the "
                                "real placement (model.cuda() before generate)"},
        "isolation": {"check": "corpus_check.split_isolation_problems(120 train groups, 30 dev groups)",
                      "result": "pass"},
        "decode": {"greedy": True, "maxNewTokens": MAX_NEW, "numBeams": 1},
        "tokenizer": {"legacy": False,
                      "note": "same pin as training and the zero-shot baseline"},
        "judge": "corpus_check.check_row over the dev row's own plan/refs/must "
                 "(hashes recomputed for the generated text; planRefs re-expanded "
                 "to the generated sentence count)",
        "devInputs": {
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
        },
        "devGroups": sorted({g for r in rows if r["split"] == "dev"
                             for g in [r["sourceGroupId"]]}),
        "arms": arms,
        "disclaimers": [
            "unseen-input denominator only; regression inputs are reported "
            "separately and never counted as generalization",
            "quality gate closure needs broader coverage and human review",
            "Chinese naturalness is left to human review at delivery acceptance",
            "training saw the plan rendering; zero-shot base did not",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
