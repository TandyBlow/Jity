# N4 sentence finetune, round 1 (deliverable-3 process trial).
#
# Scope per the approved plan: this is a PROCESS trial on the reviewed
# 52-row corpus — 48 train rows (24 groups x seed+rewrite), 4 dev rows held
# out by sourceGroupId; model quality is accepted SEPARATELY from this run.
# Not presupposed to be enough to train 77M well (plan-table §4).
#
# Fixed settings (plan-table §6):
# - tokenizer: T5Tokenizer(legacy=False) — same pin as the re-verified
#   zero-shot baseline (randeng_smoke v3) and the eval script
# - task: fact-plan text -> narration text, input rendered by n4_render
#   (the single shared renderer; runtime N4 prompts must match)
# - full-parameter finetune on the local Randeng-T5-77M weights, cuda
# - greedy decode at eval; quality verdicts are NOT issued here
#
# Usage: python experiments/world-components/n4_corpus/train_n4_sentence.py
# Output: assets/n4-finetune/r1/ (checkpoint, NOT committed) +
#         artifacts/world-components/n4-finetune-train-r1.json (config+loss log)

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
SEEDS = HERE / "corpus.seeds.jsonl"
REWRITES = HERE / "rewrites.jsonl"
BASE_MODEL = HERE.parent / "assets" / "randeng-t5-77m"
OUT_DIR = HERE.parent / "assets" / "n4-finetune" / "r1"
REPORT = REPO / "artifacts" / "world-components" / "n4-finetune-train-r1.json"

SEED = 20261029
EPOCHS = 6
BATCH = 8
LR = 1e-4
MAX_IN = 128
MAX_OUT = 64


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_rows():
    rows = {}
    for f in (SEEDS, REWRITES):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows.setdefault(r["sourceGroupId"], []).append(r)
    all_rows = [r for ms in rows.values() for r in ms]
    # shared isolation assertion (review round 9): train/dev group sets must
    # be disjoint with the expected shape — same function the eval side runs
    problems = corpus_check.split_isolation_problems(all_rows, 24, 6)
    if problems:
        for p in problems:
            print("ISOLATION:", p)
        sys.exit(2)
    train, dev = [], []
    for gid, members in rows.items():
        split = members[0]["split"]
        for r in members:
            pair = {
                "groupId": gid,
                "rowOrigin": r["rowOrigin"],
                "input": render_input(r["plan"]),
                "target": r["text"],
                "rowHash": sha(r["text"] + r["hashes"]["plan"]),
            }
            (dev if split == "dev" else train).append(pair)
    return train, dev


def main() -> None:
    assert torch.cuda.is_available(), "process trial runs on cuda per plan"
    train, dev = load_rows()
    print(f"train pairs: {len(train)}  dev pairs: {len(dev)}")
    assert len(train) == 48 and len(dev) == 12, "group shape changed"

    torch.manual_seed(SEED)
    tokenizer = T5Tokenizer(vocab_file=str(BASE_MODEL / "spiece.model"), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(BASE_MODEL), torch_dtype=torch.float32)
    model.cuda()

    enc = tokenizer([p["input"] for p in train], padding=True, truncation=True,
                    max_length=MAX_IN, return_tensors="pt")
    dec = tokenizer([p["target"] for p in train], padding=True, truncation=True,
                    max_length=MAX_OUT, return_tensors="pt")
    labels = dec["input_ids"].clone()
    labels[labels == tokenizer.pad_token_id] = -100
    enc = {k: v.cuda() for k, v in enc.items()}
    labels = labels.cuda()

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    model.train()
    log = []
    t0 = time.perf_counter()
    steps_per_epoch = (len(train) + BATCH - 1) // BATCH
    for epoch in range(EPOCHS):
        perm = torch.randperm(len(train))
        total = 0.0
        for s in range(0, len(train), BATCH):
            idx = perm[s:s + BATCH]
            batch = {k: v[idx] for k, v in enc.items()}
            out = model(**batch, labels=labels[idx])
            out.loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            total += out.loss.item()
        entry = {"epoch": epoch + 1, "meanLoss": round(total / steps_per_epoch, 4),
                 "seconds": round(time.perf_counter() - t0, 1)}
        log.append(entry)
        print(entry)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUT_DIR)
    tokenizer.save_pretrained(OUT_DIR)
    checkpoint_hashes = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:16]
                         for f in sorted(OUT_DIR.iterdir()) if f.is_file()}

    report = {
        "purpose": "n4 finetune process trial r1 (quality accepted separately)",
        "model": {"base": str(BASE_MODEL), "hfId": "IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese",
                  "paramCount": sum(p.numel() for p in model.parameters())},
        "provenance": {"corpusAndRenderer": corpus_hashes(),
                       "checkpointSha256_16": checkpoint_hashes},
        "tokenizer": {"class": "T5Tokenizer", "legacy": False,
                      "note": "same pin as zero-shot baseline v3 and eval script"},
        "environment": {"python": sys.version.split()[0], "torch": torch.__version__,
                        "transformers": transformers.__version__,
                        "device": torch.cuda.get_device_name(0)},
        "isolation": {"check": "corpus_check.split_isolation_problems(24 train groups, 6 dev groups)",
                      "result": "pass"},
        "data": {"trainPairs": len(train), "devPairs": len(dev),
                 "devGroupIds": sorted({p["groupId"] for p in dev}),
                 "renderer": "n4_render.render_input (shared train/inference)",
                 "trainRowKinds": sorted({p["rowOrigin"] for p in train})},
        "hyper": {"seed": SEED, "epochs": EPOCHS, "batch": BATCH, "lr": LR,
                  "maxInput": MAX_IN, "maxOutput": MAX_OUT, "optimizer": "AdamW",
                  "device": "cuda", "precision": "fp32"},
        "lossLog": log,
        "checkpoint": str(OUT_DIR),
        "disclaimers": [
            "process trial only; not presupposed to be enough for 77M",
            "no quality verdict here; dev eval is eval_n4_finetune.py, accepted separately",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
