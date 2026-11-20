# Freeze the experiment before any weight is initialised.
#
# Everything that decides what the model can learn is registered here, once,
# with a hash: the label order, the serializer, the criterion text, the model
# and trainer source, the split rules, the masks, the class weights, the seed
# and the order "seed first, then build". `train.py` refuses to start if any
# registered file changed or if the seed rule is violated.
#
# Usage:
#   python freeze.py            # create freeze.json (refuses if it already exists)
#   python freeze.py --rev      # write a new revision, keeping the old file
#   python freeze.py --verify   # check the current tree against freeze.json

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SHARED = ROOT / "results" / "action-dataset-20261111"
FREEZE = HERE / "freeze.json"

REGISTERED_FILES = [
    "labels.py",
    "serialize.py",
    "dataset.py",
    "model.py",
    "train.py",
    "evaluate.py",
    "measure_tokens.py",
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build() -> dict:
    label_path = SHARED / "labels-v1.json"
    criterion_path = SHARED / "criterion.txt"
    labels = json.loads(label_path.read_text(encoding="utf-8"))
    fine = [predicate for group in labels["groups"] for predicate in group["predicates"]]
    return {
        "experiment": "action-next-step",
        "version": "v1",
        "role": "04-settlement independent experiment; product protocol untouched",
        "criterion": {
            "path": str(criterion_path),
            "sha256": sha(criterion_path),
            "text": criterion_path.read_text(encoding="utf-8").strip(),
        },
        "labels": {
            "path": str(label_path),
            "sha256": sha(label_path),
            "fine": len(fine),
            "coarse": len(labels["groups"]),
            "order": "groups in file order, predicates in file order",
            "skipRepresentation": "steps = []",
            "playerFallbackLabel": labels["playerFallbackLabel"],
            "coarseIsReportingOnly": True,
        },
        "sources": {name: sha(HERE / name) for name in REGISTERED_FILES if (HERE / name).exists()},
        "backbone": {
            "name": "MiniRBT-H256",
            "dirArgument": "--base (resolved on the HPC login node; not present on this machine)",
            "expectedWeightsSha256": "6728ca573fd5197f28198eb7e6119a76e4d5dc626f953fca8c0dc5ba2798f9fc",
            "expectedWeightsNote": "records the weights file the previous component line trained against; train.py reports the actual sha it loaded",
            "tokenizer": "BertTokenizer from the same directory; the tokenizer files are hashed into the run report",
        },
        "seed": {
            "value": 20261111,
            "rule": "torch.manual_seed + random.seed + numpy seed (when numpy is imported) happen BEFORE the encoder is loaded and BEFORE any new head parameter exists",
            "why": "the reference trainer seeded after model construction; that ordering is not reused",
        },
        "arms": {
            "primary": "frozen_encoder",
            "secondary": "unfrozen_encoder",
            "selection": "validation only; the test set is opened once, after the arm and hyperparameters are fixed",
            "reporting": "the two arms are reported separately; they are never averaged",
        },
        "hyper": {
            "batch": 16,
            "epochsMax": 12,
            "lrHeadFrozen": 0.001,
            "lrFull": 0.00003,
            "weightDecay": 0.01,
            "dropout": 0.1,
            "optimizer": "AdamW",
            "earlyStop": "validation primaryGroupHit, patience 3 epochs, best checkpoint kept",
            "maxLen": None,
            "maxLenRule": "measure_tokens.py reports the 100th percentile over train+validation; maxLen = that value rounded UP to a multiple of 32, capped at 384; if the 100th percentile exceeds 384 the run stops and reports the count instead of truncating",
        },
        "loss": {
            "step": "CrossEntropyLoss(weight=stepWeights) over 3 classes [skip, one, two]",
            "action": "CrossEntropyLoss(weight=fineWeights) per step slot, masked where the row has no such step",
            "object": "CrossEntropyLoss over [null, candidate_1..candidate_n], masked where the row has no such step; padding scores are masked by the candidate mask",
            "stepWeights": [0.3, 1.0, 1.0],
            "fineWeightRule": "weight_i = clip(median(count)/count_i, 1.0, 1.5); computed from the TRAIN split only and printed in the run report",
            "objectNullWeight": 1.0,
            "note": "skip stays a real learnable class; skip rows contribute no action/object loss and one-step rows contribute no slot-2 loss",
        },
        "data": {
            "trainRows": 300,
            "trainSource": "13-action-dataset; 01 reviewed every row; 03 blind second review of 10%",
            "validationSource": "separate rows, isolated by goal family (see dataset.check_split_isolation)",
            "testSource": "01-frozen, 15 withheld goals, opened exactly once after the arm and hyperparameters are fixed",
            "noCrossSplitGoal": True,
            "noSyntheticTrainingRows": "synthetic fixtures exist only under tests/ and are labelled fixture",
        },
        "metrics": {
            "primaryGroupHit": "coarse group of step 1 vs the frozen acceptable group set",
            "fullHit": "exact steps list: count, order, fine predicate, object",
            "skipRecall": "skips predicted / skips in the frozen answer",
            "wrongActionRate": "non-skip rows whose step-1 group is not acceptable",
            "nonSkipGroupAccuracy": "group accuracy over non-skip rows",
            "groupMacro": "12-group macro average over non-skip rows",
            "perGoal": "one row per withheld goal with its scenario count",
            "thresholds": {"continue": 0.6, "stop": 0.4},
        },
        "notClaimed": [
            "a 12-group hit is not a full Y",
            "one 300-row version is not proof that the task is unlearnable",
            "an experimental classifier is not a product protocol change",
        ],
    }


def freeze_id(payload: dict) -> str:
    body = {key: value for key, value in payload.items() if key not in ("frozenAt", "freezeId", "supersedes")}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rev", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    missing = [name for name in REGISTERED_FILES if not (HERE / name).exists()]
    if missing:
        print(f"REFUSED: registered source missing: {missing}", file=sys.stderr)
        return 2
    payload = build()
    if args.verify:
        if not FREEZE.exists():
            print("REFUSED: no freeze.json", file=sys.stderr)
            return 2
        current = json.loads(FREEZE.read_text(encoding="utf-8"))
        if current["freezeId"] != freeze_id(current):
            print("REFUSED: freeze.json does not match its own freezeId", file=sys.stderr)
            return 2
        drift = [
            (name, current["sources"][name], sha(HERE / name))
            for name in REGISTERED_FILES if current["sources"].get(name) != sha(HERE / name)
        ]
        if current["labels"]["sha256"] != sha(SHARED / "labels-v1.json"):
            drift.append(("labels-v1.json", current["labels"]["sha256"], sha(SHARED / "labels-v1.json")))
        if drift:
            for name, before, now in drift:
                print(f"DRIFT {name}: {before[:16]} -> {now[:16]}", file=sys.stderr)
            return 2
        print(f"OK freezeId {current['freezeId'][:16]} matches {len(REGISTERED_FILES)} sources")
        return 0
    if FREEZE.exists() and not args.rev:
        print(f"REFUSED: {FREEZE.name} already exists (use --rev to supersede)", file=sys.stderr)
        return 2
    payload["frozenAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    if args.rev and FREEZE.exists():
        previous = json.loads(FREEZE.read_text(encoding="utf-8"))
        payload["supersedes"] = previous.get("freezeId")
    payload["freezeId"] = freeze_id(payload)
    FREEZE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"frozen {payload['freezeId'][:16]} -> {FREEZE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
