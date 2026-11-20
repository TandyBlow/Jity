# N4 fitting diagnosis (review round 9, step 1 of the next phase).
#
# Question: can MORE TRAINING fix the real errors on the TRAINING plans
# themselves (empty/chain/multi among the 24 train plans currently pass
# 11/24 under the strict recognizer), or is the bottleneck data?
# r1 trained only 36 optimizer steps; this run goes to 360 steps from the
# SAME base and config, saving a checkpoint every 60 steps and evaluating
# train (24 plans) + dev (6 plans) at each point.
#
# Counting per the review correction: plans are counted INDEPENDENTLY — a
# group's seed and rewrite rows share one rendered input, so 48 train rows
# = 24 plans and 12 dev rows = 6 plans. Verdicts come from the same
# recognizer judge as eval_n4_finetune (refs re-expanded, hashes recomputed;
# v7 equivalence rules active). Human review is reported separately and is
# NOT reproduced here.
#
# All generation and evaluation run on CUDA (r1's eval silently ran on CPU
# — fixed there and never repeated here).
#
# Usage: python experiments/world-components/n4_corpus/diag_n4_fitting.py
# Output: assets/n4-finetune/diag-step<N>/ (checkpoints, untracked) +
#         artifacts/world-components/n4-fitting-diag.json

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
from eval_n4_finetune import judge  # noqa: E402  (same recognizer judge)

REPO = HERE.parent.parent.parent
BASE_MODEL = HERE.parent / "assets" / "randeng-t5-77m"
DIAG_ROOT = HERE.parent / "assets" / "n4-finetune"
REPORT = REPO / "artifacts" / "world-components" / "n4-fitting-diag.json"

SEED = 20261029
TOTAL_STEPS = 360
CHECK_EVERY = 60
BATCH = 8
LR = 1e-4
MAX_IN = 128
MAX_OUT = 64
MAX_NEW = 64


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_plans():
    """One entry per INDEPENDENT plan (rows of a group share the plan)."""
    groups = {}
    for f in (HERE / "corpus.seeds.jsonl", HERE / "rewrites.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                groups.setdefault(r["sourceGroupId"], []).append(r)
    problems = corpus_check.split_isolation_problems(
        [r for ms in groups.values() for r in ms], 24, 6)
    assert not problems, f"isolation drift: {problems}"
    train_plans, dev_plans = [], []
    for gid, ms in groups.items():
        plan_ref = ms[0]
        targets = [m["text"] for m in ms]
        entry = {"groupId": gid, "input": render_input(plan_ref["plan"]),
                 "plan": plan_ref["plan"], "row": plan_ref}
        (dev_plans if plan_ref["split"] == "dev" else train_plans).append(entry)
    return train_plans, dev_plans, targets_of(groups)


def targets_of(groups):
    """Training pairs stay row-level (seed+rewrite = two targets per plan)."""
    pairs = []
    for gid, ms in groups.items():
        if ms[0]["split"] != "train":
            continue
        for r in ms:
            pairs.append({"input": render_input(r["plan"]), "target": r["text"]})
    return pairs


def evaluate(model, tokenizer, plans, arm_label):
    results = []
    for p in plans:
        inputs = tokenizer(p["input"], return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=MAX_NEW,
                                 num_beams=1, do_sample=False)
        text = tokenizer.decode(out[0], skip_special_tokens=True)
        verdict = judge(p["row"], text)
        results.append({"groupId": p["groupId"], "output": text,
                        "outputTokens": int(out.shape[1]), **verdict})
    counts = {"pass": 0, "review": 0, "fail": 0}
    for x in results:
        counts[x["verdict"]] += 1
    print(f"  [{arm_label}] {counts['pass']}/{len(plans)} plans pass "
          f"({counts['review']} review, {counts['fail']} fail)")
    return {"counts": counts, "rows": results}


def main() -> None:
    assert torch.cuda.is_available()
    train_plans, dev_plans, pairs = load_plans()
    print(f"train plans: {len(train_plans)}  dev plans: {len(dev_plans)}  "
          f"train pairs: {len(pairs)}")
    torch.manual_seed(SEED)
    tokenizer = T5Tokenizer(vocab_file=str(BASE_MODEL / "spiece.model"), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(BASE_MODEL), torch_dtype=torch.float32)
    model.cuda()
    enc = tokenizer([p["input"] for p in pairs], padding=True, truncation=True,
                    max_length=MAX_IN, return_tensors="pt")
    dec = tokenizer([p["target"] for p in pairs], padding=True, truncation=True,
                    max_length=MAX_OUT, return_tensors="pt")
    labels = dec["input_ids"].clone()
    labels[labels == tokenizer.pad_token_id] = -100
    enc = {k: v.cuda() for k, v in enc.items()}
    labels = labels.cuda()
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)

    report = {
        "purpose": "fitting diagnosis: does more training fix train-plan errors?",
        "provenance": {"corpusAndRenderer": corpus_hashes()},
        "environment": {"python": sys.version.split()[0], "torch": torch.__version__,
                        "transformers": transformers.__version__, "device": "cuda",
                        "deviceName": torch.cuda.get_device_name(0)},
        "config": {"seed": SEED, "totalSteps": TOTAL_STEPS, "checkEvery": CHECK_EVERY,
                   "batch": BATCH, "lr": LR, "optimizer": "AdamW",
                   "tokenizerLegacy": False, "precision": "fp32"},
        "counting": "per independent plan (48 train rows = 24 plans; 12 dev rows = 6 plans)",
        "judge": "eval_n4_finetune.judge (recognizer, refs re-expanded; "
                 "v7 equivalence rules active; human verdicts are separate)",
        "points": [],
    }
    model.train()
    step = 0
    t0 = time.perf_counter()
    perm = torch.randperm(len(pairs))
    ptr = 0
    losses = []
    while step < TOTAL_STEPS:
        if ptr + BATCH > len(pairs):
            perm = torch.randperm(len(pairs))
            ptr = 0
        idx = perm[ptr:ptr + BATCH]
        ptr += BATCH
        batch = {k: v[idx] for k, v in enc.items()}
        out = model(**batch, labels=labels[idx])
        out.loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        losses.append(round(out.loss.item(), 4))
        step += 1
        if step % CHECK_EVERY == 0:
            model.eval()
            ckpt = DIAG_ROOT / f"diag-step{step}"
            model.save_pretrained(ckpt)
            tokenizer.save_pretrained(ckpt)
            tr = evaluate(model, tokenizer, train_plans, f"step{step} train")
            dv = evaluate(model, tokenizer, dev_plans, f"step{step} dev")
            model.train()
            point = {"step": step,
                     # v8: true last-60-step window (the r1-diag report shipped
                     # this field as a cumulative average — renamed there)
                     "meanLossLast60": round(sum(losses[-60:]) / min(len(losses), 60), 4),
                     "meanLossCumulative": round(sum(losses) / len(losses), 4),
                     "seconds": round(time.perf_counter() - t0, 1),
                     "train": tr, "dev": dv,
                     "checkpoint": str(ckpt),
                     "checkpointSha256_16": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:16]
                                             for f in sorted(ckpt.iterdir()) if f.is_file()}}
            report["points"].append(point)

    report["conclusionInputs"] = {
        "question": "does 60->360 steps fix train-plan errors (empty/chain/multi)?",
        "attribution": "under the CURRENT training distribution, steps 60-360 did "
                       "not resolve the failing dev instance (step 60 omitted "
                       "personality/sanity; later checkpoints produce the direction "
                       "error); this SUPPORTS added downward-direction coverage but "
                       "does not prove further training can never help",
        "readTogetherWith": "human verdicts (review round 9): dev 3/6 plans pass "
                            "with the appearance false-reject now equivalence-ruled",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
