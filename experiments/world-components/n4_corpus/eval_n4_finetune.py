# N4 finetune dev evaluation, round 1: two arms (base vs finetuned) on the
# 4 held-out dev rows, judged by the SAME recognizer that gates the corpus
# (corpus_check.check_row) — a generation counts as faithful only when the
# plan's mustExpress entries are recognized with value-consistent parses.
#
# Decode: greedy, max_new_tokens=64, tokenizer legacy=False (same pin as
# training and the zero-shot baseline). No quality verdicts beyond the
# recognizer's three states; human review of the generated texts happens at
# delivery acceptance.
#
# Usage: python experiments/world-components/n4_corpus/eval_n4_finetune.py
# Output: artifacts/world-components/n4-finetune-eval-r1.json

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
FINETUNED = HERE.parent / "assets" / "n4-finetune" / "r1"
REPORT = REPO / "artifacts" / "world-components" / "n4-finetune-eval-r1.json"
MAX_NEW = 64


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_dev():
    groups = {}
    for f in (HERE / "corpus.seeds.jsonl", HERE / "rewrites.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                groups.setdefault(r["sourceGroupId"], []).append(r)
    return [m for gid, ms in groups.items() if ms[0]["split"] == "dev" for m in ms]


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


def main() -> None:
    rows = []
    for f in (HERE / "corpus.seeds.jsonl", HERE / "rewrites.jsonl"):
        rows += [json.loads(line) for line in
                 f.read_text(encoding="utf-8").splitlines() if line.strip()]
    problems = corpus_check.split_isolation_problems(rows, 120, 30)
    if problems:
        for p in problems:
            print("ISOLATION:", p)
        sys.exit(2)
    dev = load_dev()
    print(f"dev rows: {len(dev)} (groups {sorted({r['sourceGroupId'] for r in dev})})")
    tokenizer = T5Tokenizer(vocab_file=str(BASE_MODEL / "spiece.model"), legacy=False)

    arms = {}
    for arm, path in (("base", BASE_MODEL), ("finetuned", FINETUNED)):
        model = T5ForConditionalGeneration.from_pretrained(str(path), torch_dtype=torch.float32)
        model.cuda()  # v7: review found r1 silently ran this eval on CPU
        model.eval()
        results = []
        for r in dev:
            prompt = render_input(r["plan"])
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            t0 = time.perf_counter()
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=MAX_NEW,
                                     num_beams=1, do_sample=False)
            wall = round(time.perf_counter() - t0, 2)
            text = tokenizer.decode(out[0], skip_special_tokens=True)
            verdict = judge(r, text)
            results.append({
                "sourceGroupId": r["sourceGroupId"], "rowOrigin": r["rowOrigin"],
                "input": prompt, "output": text, "outputTokens": int(out.shape[1]),
                "wallSeconds": wall, **verdict,
            })
            print(f"[{arm}] {r['sourceGroupId']} ({r['rowOrigin']}) {wall}s "
                  f"-> {verdict}: {text[:60]}")
        counts = {"pass": 0, "review": 0, "fail": 0}
        for x in results:
            counts[x["verdict"]] += 1
        arms[arm] = {"verdicts": counts, "rows": results,
                     "meanWall": round(sum(x["wallSeconds"] for x in results) / len(results), 2),
                     "meanTokens": round(sum(x["outputTokens"] for x in results) / len(results), 1)}
        del model

    report = {
        "purpose": "n4 finetune dev eval (recognizer-judged; quality accepted separately)",
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
        "devGroups": sorted({r["sourceGroupId"] for r in dev}),
        "arms": arms,
        "disclaimers": [
            "dev-group count is the current expansion's; quality gate closure needs "
            "broader coverage and human review",
            "Chinese naturalness is left to human review at delivery acceptance",
            "training saw the plan rendering; zero-shot base did not",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
