# N5 fact-sentence relation head (commit 3): MiniRBT-H256 + mean-pooling +
# linear(3) over the FROZEN pair corpus (support / contradiction / unknown).
#
# Input format (frozen HERE before training; the browser side must match
# byte-for-byte):
#     句子：{sentence}事实：{fact_desc}关系：
# (no EOS/special-token games — MiniRBT is an encoder; [CLS]/pad handling
# is the tokenizer's.)
#
# Decision rule (frozen): p = softmax(logits); support if p[support] >=
# T_SUPPORT; else contradiction if p[contradiction] >= T_CONTRADICT; else
# unknown (待核). The thresholds are FIXED ON THE DEV SPLIT by the
# pre-registered rule in eval_n5_head.py before the test split is touched.
#
# Trains ON THE HPC (the standing training directive). The trainer refuses
# to run if the frozen test file's sha differs from the freeze
# registration — the test set cannot move after the freeze.
#
# Usage (HPC): python train_n5_head.py --epochs 8
# Output: ckpt-n5/ (head weights) + train-n5-report.json

import argparse
import hashlib
import json
import pathlib
import random
import sys
import time

import torch
from torch import nn
from transformers.models.bert.modeling_bert import BertModel

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "n4_corpus_v2"))
sys.path.insert(0, str(HERE.parent / "n4_corpus"))

from build_n5_pairs import fact_desc  # noqa: E402  (frozen pair text)

PAIRS = HERE / "corpus_v2" / "n5"
BASE = pathlib.Path("base/minirbt-h256")
SEED = 20261102
BATCH = 32
LR = 3e-5
MAX_LEN = 96
LABELS = {"support": 0, "contradiction": 1, "unknown": 2}


def pair_text(pair: dict) -> str:
    return f"句子：{pair['sentence']}事实：{fact_desc(pair['fact'])}关系："


def sha_file(p) -> str:
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


class RelationHead(nn.Module):
    """Mean-pooling over the encoder's last layer + a linear three-class
    head. The head weights ship SEPARATELY from the base so the model and
    head hashes can be pinned independently."""

    def __init__(self, base_dir, hidden=256, n_classes=3):
        super().__init__()
        self.encoder = BertModel.from_pretrained(base_dir)
        self.dropout = nn.Dropout(0.1)
        self.classifier = nn.Linear(hidden, n_classes)

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        out = self.encoder(input_ids=input_ids,
                           attention_mask=attention_mask,
                           token_type_ids=token_type_ids)
        mask = attention_mask.unsqueeze(-1).to(out.last_hidden_state.dtype)
        pooled = (out.last_hidden_state * mask).sum(1) / \
            mask.sum(1).clamp(min=1e-9)
        return self.classifier(self.dropout(pooled))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--base", default=str(BASE))
    parser.add_argument("--out", default="ckpt-n5")
    args = parser.parse_args()

    freeze = json.loads((PAIRS / "test-freeze.json").read_text(
        encoding="utf-8"))
    got = sha_file(PAIRS / "test.jsonl")
    if got != freeze["sha256"]:
        print(f"REFUSED: n5 test sha {got[:16]} != frozen "
              f"{freeze['sha256'][:16]} — the test set moved after the freeze")
        return 2
    rows = [json.loads(l) for l in
            (PAIRS / "train.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    train = [r for r in rows if r["split"] == "train"]
    dev = [r for r in rows if r["split"] == "dev"]
    print(f"train {len(train)} / dev {len(dev)} pairs")

    from transformers.models.bert.tokenization_bert import BertTokenizer
    tok = BertTokenizer.from_pretrained(args.base)
    model = RelationHead(args.base).cuda()
    torch.manual_seed(SEED)
    random.seed(SEED)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    weights = torch.tensor([1.0, 1.2, 0.8]).cuda()  # mild class balance
    lossf = nn.CrossEntropyLoss(weight=weights)

    def encode(pairs):
        texts = [pair_text(p) for p in pairs]
        enc = tok(texts, padding=True, truncation=True, max_length=MAX_LEN,
                  return_tensors="pt")
        y = torch.tensor([LABELS[p["label"]] for p in pairs])
        return enc, y

    order = list(range(len(train)))
    steps = 0
    t0 = time.perf_counter()
    losses = []
    model.train()
    for epoch in range(args.epochs):
        random.shuffle(order)
        for s in range(0, len(order), BATCH):
            idx = order[s:s + BATCH]
            enc, y = encode([train[i] for i in idx])
            enc = {k: v.cuda() for k, v in enc.items()}
            logits = model(**enc)
            loss = lossf(logits, y.cuda())
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            steps += 1
            losses.append(round(float(loss), 4))
            if steps % 50 == 0:
                print(f"step {steps} loss {loss:.4f}", flush=True)
    wall = round(time.perf_counter() - t0, 1)
    out_dir = pathlib.Path(args.out)
    model.eval()
    torch.save({"classifier": model.classifier.state_dict()}, "head-n5.pt")
    model.encoder.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))
    report = {
        "purpose": "N5 fact-sentence relation head (commit 3)",
        "inputFormat": "句子：{sentence}事实：{fact_desc}关系：",
        "labels": LABELS,
        "base": {"dir": args.base, "sha256": sha_file(
            pathlib.Path(args.base) / "pytorch_model.bin")},
        "data": {"train": len(train), "dev": len(dev),
                 "pairsSha256": sha_file(PAIRS / "train.jsonl"),
                 "testFrozen": {"rows": freeze["rows"],
                                "sha256": freeze["sha256"]}},
        "hyper": {"seed": SEED, "epochs": args.epochs, "batch": BATCH,
                  "lr": LR, "maxLen": MAX_LEN, "optimizer": "AdamW",
                  "classWeights": [1.0, 1.2, 0.8],
                  "device": torch.cuda.get_device_name(0)},
        "lossFirst5": losses[:5], "lossLast5": losses[-5:],
        "wallSeconds": wall,
    }
    pathlib.Path("train-n5-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("done:", json.dumps(report["hyper"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
