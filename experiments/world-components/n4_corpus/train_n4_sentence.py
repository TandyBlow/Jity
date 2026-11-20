# N4 sentence finetune (deliverable-3 process trial).
#
# Round 12 (review requirement): two-tier comparison entry. `--tier small`
# trains on the 60 small-tier sources (240 pairs), `--tier large` on all 120
# sources (480 pairs); both run the SAME number of optimizer steps (360,
# batch 8) so the comparison is step-matched, not epoch-matched. Artifact
# paths follow --run-tag (r2-small / r2-large), keeping checkpoints and
# reports separate.
#
# Scope per the approved plan: process trial on the reviewed N4 corpus. The
# committed r1 archive was produced on the earlier 52-row corpus (48 train
# rows / 24 groups, 4 dev rows) and is pinned by its corpus hashes; running
# on a different corpus MUST use a new tag, e.g. `--run-tag r2-small`
# (the script aborts on an r1/corpus-hash mismatch). Model quality is
# accepted separately from this run and is not presupposed to be enough to
# train 77M well (plan-table §4).
#
# Fixed settings (plan-table §6):
# - tokenizer: T5Tokenizer(legacy=False) — same pin as the re-verified
#   zero-shot baseline (randeng_smoke v3) and the eval script
# - task: fact-plan text -> narration text, input rendered by n4_render
#   (the single shared renderer; runtime N4 prompts must match)
# - full-parameter finetune on the local Randeng-T5-77M weights, cuda
# - greedy decode at eval; quality verdicts are NOT issued here
#
# Usage: python experiments/world-components/n4_corpus/train_n4_sentence.py \
#          --tier small --run-tag r2-small
#        python experiments/world-components/n4_corpus/train_n4_sentence.py \
#          --tier large --run-tag r2-large
# Output: assets/n4-finetune/<tag>/ (checkpoint, NOT committed) +
#         artifacts/world-components/n4-finetune-train-<tag>.json

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

# Determinism (joint decision D3). The frozen r3-direction checkpoint was
# trained before these flags were added, so a rebuild is not promised to be
# bitwise identical; acceptance is a holdout re-run (see
# n4-integration-package.md §3). Flags are recorded for future rebuilds.
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
DETERMINISM = {
    "cudnnDeterministic": bool(torch.backends.cudnn.deterministic),
    "cudnnBenchmark": bool(torch.backends.cudnn.benchmark),
    "cudnnVersion": torch.backends.cudnn.version(),
    "cudaVersion": torch.version.cuda,
}

REPO = HERE.parent.parent.parent
SEEDS = HERE / "corpus.seeds.jsonl"
REWRITES = HERE / "rewrites.jsonl"
BASE_MODEL = HERE.parent / "assets" / "randeng-t5-77m"


def arg_value(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


RUN_TAG = arg_value("--run-tag", "r1")
TIER = arg_value("--tier", "large")
if TIER not in ("small", "large"):
    sys.exit(f"--tier must be small|large, got {TIER!r}")
OUT_DIR = HERE.parent / "assets" / "n4-finetune" / RUN_TAG
REPORT = REPO / "artifacts" / "world-components" / f"n4-finetune-train-{RUN_TAG}.json"

if RUN_TAG == "r1" and REPORT.exists():
    pinned = json.loads(REPORT.read_text(encoding="utf-8"))
    recorded = pinned["provenance"]["corpusAndRenderer"]["corpus.seeds.jsonl"]
    if recorded != corpus_hashes()["corpus.seeds.jsonl"]:
        sys.exit("r1 archive is pinned to the earlier corpus; "
                 "pass --run-tag r2-small / r2-large for the expanded corpus")

SEED = 20261029
TRAIN_STEPS = 360
BATCH = 8
LR = 1e-4
MAX_IN = 128
MAX_OUT = 64
TIER_GROUPS = {"small": 60, "large": 120}
TIER_ROWS = {"small": 240, "large": 480}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_rows(tier: str):
    rows = {}
    for f in (SEEDS, REWRITES):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows.setdefault(r["sourceGroupId"], []).append(r)
    all_rows = [r for ms in rows.values() for r in ms]
    # shared isolation assertion (review round 9): train/dev group sets must
    # be disjoint with the expected corpus shape — same function the eval
    # side runs. Tier shape is asserted separately below.
    problems = corpus_check.split_isolation_problems(all_rows, 120, 30)
    if problems:
        for p in problems:
            print("ISOLATION:", p)
        sys.exit(2)

    allowed = {"small"} if tier == "small" else {"small", "large"}
    train, dev = [], []
    for gid, members in rows.items():
        split = members[0]["split"]
        tiers = {m["tier"] for m in members}
        if len(tiers) != 1:
            sys.exit(f"tier varies within group {gid}: {sorted(tiers)}")
        for r in members:
            pair = {
                "groupId": gid,
                "tier": r["tier"],
                "rowOrigin": r["rowOrigin"],
                "input": render_input(r["plan"]),
                "target": r["text"],
                "rowHash": sha(r["text"] + r["hashes"]["plan"]),
            }
            (dev if split == "dev" else train).append(pair)
    train = [p for p in train if p["tier"] in allowed]
    train_groups = {p["groupId"] for p in train}
    if len(train) != TIER_ROWS[tier] or len(train_groups) != TIER_GROUPS[tier]:
        sys.exit(f"tier {tier}: expected {TIER_ROWS[tier]} rows / "
                 f"{TIER_GROUPS[tier]} groups, got {len(train)} / {len(train_groups)}")
    return train, dev


def main() -> None:
    assert torch.cuda.is_available(), "process trial runs on cuda per plan"
    train, dev = load_rows(TIER)
    print(f"tier {TIER}: train pairs {len(train)}  dev pairs {len(dev)}  "
          f"steps {TRAIN_STEPS}")

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
    steps_done = 0
    epoch = 0
    while steps_done < TRAIN_STEPS:
        epoch += 1
        perm = torch.randperm(len(train))
        total = 0.0
        epoch_steps = 0
        for s in range(0, len(train), BATCH):
            if steps_done >= TRAIN_STEPS:
                break
            idx = perm[s:s + BATCH]
            batch = {k: v[idx] for k, v in enc.items()}
            out = model(**batch, labels=labels[idx])
            out.loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            total += out.loss.item()
            steps_done += 1
            epoch_steps += 1
        entry = {"epoch": epoch, "steps": epoch_steps,
                 "meanLoss": round(total / epoch_steps, 4),
                 "seconds": round(time.perf_counter() - t0, 1)}
        log.append(entry)
        print(entry)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUT_DIR)
    tokenizer.save_pretrained(OUT_DIR)
    checkpoint_hashes = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:16]
                         for f in sorted(OUT_DIR.iterdir()) if f.is_file()}

    report = {
        "purpose": f"n4 finetune {TIER}-tier trial {RUN_TAG} "
                   f"({TRAIN_STEPS} steps; quality accepted separately)",
        "model": {"base": str(BASE_MODEL), "hfId": "IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese",
                  "paramCount": sum(p.numel() for p in model.parameters())},
        "provenance": {"corpusAndRenderer": corpus_hashes(),
                       "checkpointSha256_16": checkpoint_hashes},
        "tokenizer": {"class": "T5Tokenizer", "legacy": False,
                      "note": "same pin as zero-shot baseline v3 and eval script"},
        "environment": {"python": sys.version.split()[0], "torch": torch.__version__,
                        "transformers": transformers.__version__,
                        "device": torch.cuda.get_device_name(0),
                        "determinism": DETERMINISM},
        "isolation": {"check": "corpus_check.split_isolation_problems(120 train groups, 30 dev groups) "
                               f"+ tier filter {TIER} ({TIER_GROUPS[TIER]} groups)",
                      "result": "pass"},
        "data": {"tier": TIER,
                 "trainPairs": len(train), "trainGroups": len({p["groupId"] for p in train}),
                 "devPairs": len(dev),
                 "devGroupIds": sorted({p["groupId"] for p in dev}),
                 "renderer": "n4_render.render_input (shared train/inference)",
                 "trainRowKinds": sorted({p["rowOrigin"] for p in train}),
                 "tiersIncluded": sorted({p["tier"] for p in train})},
        "hyper": {"seed": SEED, "steps": TRAIN_STEPS, "epochsRun": epoch,
                  "batch": BATCH, "lr": LR,
                  "stepsPerEpoch": steps_per_epoch,
                  "maxInput": MAX_IN, "maxOutput": MAX_OUT, "optimizer": "AdamW",
                  "device": "cuda", "precision": "fp32"},
        "lossLog": log,
        "checkpoint": str(OUT_DIR),
        "disclaimers": [
            "process trial only; not presupposed to be enough for 77M",
            "small/large share steps and hyperparameters; only training data differs",
            "no quality verdict here; dev eval is eval_n4_finetune.py, accepted separately",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
