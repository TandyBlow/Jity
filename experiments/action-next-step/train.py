# Train the next-action classifier on the HPC. Never on the local 4060.
#
# Order of operations is part of the freeze:
#   1. verify freeze.json against the current tree (refuses on drift)
#   2. verify the token-length file matches the registered rule
#   3. set every seed
#   4. ONLY THEN load the encoder and build the heads
#   5. train with masked, class-weighted losses
#   6. pick the epoch by validation only
#
# Usage (HPC login node or a CPU-only batch job for a dry run):
#   python train.py --base base/minirbt-h256 --train data/train.jsonl \
#       --validation data/validation.jsonl --token-lengths token-lengths.json \
#       --arm frozen_encoder --out runs/arm-frozen
#
# A dry run with a tiny encoder is how the mechanism is tested on CPU:
#   python train.py ... --dry-run-tiny --train tests/fixture/train.jsonl \
#       --validation tests/fixture/validation.jsonl --token-lengths tests/fixture/token-lengths.json
# The tiny arm is refused for any real run because its report is labelled
# `mechanism` and its checkpoint is never exported.

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import random
import sys
import time
from typing import Dict, List, Sequence

import torch
from torch import nn

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dataset import (  # noqa: E402
    Example, build_example, check_split_isolation, collate, make_tokenizer_fn,
    object_nulls, read_rows, step_counts,
)
from labels import LabelIndex, MAX_STEPS, STEP_CLASSES, load_labels, sha256_file  # noqa: E402
from model import NextStepModel, build_encoder  # noqa: E402

FREEZE = HERE / "freeze.json"
REQUIRED_FILES = ["labels.py", "serialize.py", "dataset.py", "model.py", "train.py", "evaluate.py"]


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def freeze_id(payload: dict) -> str:
    body = {key: value for key, value in payload.items() if key not in ("frozenAt", "freezeId", "supersedes")}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def verify_freeze() -> dict:
    if not FREEZE.exists():
        raise SystemExit("REFUSED: freeze.json is missing; run freeze.py first")
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    if frozen.get("freezeId") != freeze_id(frozen):
        raise SystemExit("REFUSED: freeze.json does not match its own freezeId")
    drift = [name for name, want in frozen.get("sources", {}).items() if sha256_file(HERE / name) != want]
    if drift:
        raise SystemExit(f"REFUSED: registered source changed after the freeze: {drift}")
    if sha256_file(pathlib.Path(frozen["labels"]["path"])) != frozen["labels"]["sha256"]:
        raise SystemExit("REFUSED: the label file changed after the freeze")
    return frozen


def verify_token_lengths(path: pathlib.Path, frozen: dict) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("measured") is not True:
        raise SystemExit("REFUSED: token-lengths.json is not a measurement")
    max_len = int(data.get("maxLen") or 0)
    rule = frozen["hyper"]["maxLenRule"]
    if max_len < 32 or max_len > 384 or max_len % 32:
        raise SystemExit(f"REFUSED: registered maxLen {max_len} violates the frozen rule ({rule})")
    if int(data.get("truncatedRows") or 0) != 0:
        raise SystemExit("REFUSED: the token-length measurement reports truncation; a longer max must be registered")
    return data


def class_weights(step_values: Sequence[int], action_values: Sequence[int], frozen: dict) -> tuple[torch.Tensor, torch.Tensor]:
    step_weights = torch.tensor(frozen["loss"]["stepWeights"], dtype=torch.float)
    counts = [0] * 115
    for value in action_values:
        if value >= 0:
            counts[value] += 1
    present = [count for count in counts if count > 0]
    if not present:
        raise SystemExit("REFUSED: the train split has no actions to weight")
    median = sorted(present)[len(present) // 2]
    weights = []
    for count in counts:
        if count == 0:
            weights.append(0.0)  # a class absent from train cannot be learned; the report lists it
        else:
            weights.append(min(1.5, max(1.0, median / count)))
    return step_weights, torch.tensor(weights, dtype=torch.float)


def masked_losses(outputs: dict, batch: dict, step_weights: torch.Tensor, fine_weights: torch.Tensor) -> tuple[torch.Tensor, dict]:
    device = outputs["step_logits"].device
    loss_step = nn.functional.cross_entropy(outputs["step_logits"], batch["step"].to(device), weight=step_weights.to(device))
    parts = {"step": float(loss_step.detach())}
    total = loss_step
    for slot in range(MAX_STEPS):
        action_target = batch["actions"][:, slot]
        mask = action_target != -100
        if not bool(mask.any()):
            parts[f"action_{slot + 1}"] = None
            parts[f"object_{slot + 1}"] = None
            continue
        logits = outputs["action_logits"][:, slot][mask]
        target = action_target[mask].to(device)
        loss_action = nn.functional.cross_entropy(logits, target, weight=fine_weights.to(device))
        parts[f"action_{slot + 1}"] = float(loss_action.detach())
        total = total + loss_action
        object_target = batch["objects"][:, slot][mask].to(device)
        logits_obj = outputs["object_logits"][:, slot][mask]
        loss_object = nn.functional.cross_entropy(logits_obj, object_target)
        parts[f"object_{slot + 1}"] = float(loss_object.detach())
        total = total + loss_object
    return total, parts


def run_epoch(model, examples, tokenize, max_len, batch_size, optimizer, step_weights, fine_weights, *, train: bool) -> dict:
    model.train(train)
    order = list(range(len(examples)))
    if train:
        random.shuffle(order)
    losses: List[float] = []
    correct_steps = 0
    seen = 0
    for start in range(0, len(order), batch_size):
        chunk = [examples[index] for index in order[start:start + batch_size]]
        batch = collate(chunk, tokenize, max_len)
        device = next(model.parameters()).device
        batch = {key: value.to(device) if torch.is_tensor(value) else value for key, value in batch.items()}
        with torch.set_grad_enabled(train):
            outputs = model(
                input_ids=batch["input_ids"], attention_mask=batch["attention_mask"],
                cand_ids=batch["cand_ids"], cand_mask=batch["cand_mask"],
            )
            loss, _ = masked_losses(outputs, batch, step_weights, fine_weights)
        if train:
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            optimizer.step()
        losses.append(float(loss.detach()))
        predicted = outputs["step_logits"].argmax(-1)
        correct_steps += int((predicted == batch["step"]).sum())
        seen += len(chunk)
    return {"loss": round(sum(losses) / max(len(losses), 1), 4), "stepAccuracy": round(correct_steps / max(seen, 1), 4), "rows": seen}


def tokenizer_from(base: str):
    from transformers.models.bert.tokenization_bert import BertTokenizer

    return BertTokenizer.from_pretrained(base)


def tokenizer_files(base: pathlib.Path) -> Dict[str, str]:
    files = {}
    for name in ("vocab.txt", "tokenizer_config.json", "special_tokens_map.json", "config.json", "pytorch_model.bin"):
        path = base / name
        if path.exists():
            files[name] = sha256_file(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--train", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--token-lengths", required=True)
    parser.add_argument("--arm", choices=["frozen_encoder", "unfrozen_encoder"], default="frozen_encoder")
    parser.add_argument("--out", required=True)
    parser.add_argument("--epochs", type=int, default=0)
    parser.add_argument("--dry-run-tiny", action="store_true")
    args = parser.parse_args()

    frozen = verify_freeze()
    token_lengths = verify_token_lengths(pathlib.Path(args.token_lengths), frozen)
    max_len = int(token_lengths["maxLen"])

    labels = load_labels(frozen["labels"]["path"])
    train_rows = read_rows(args.train)
    validation_rows = read_rows(args.validation)
    for rows, name in ((train_rows, "train"), (validation_rows, "validation")):
        for row in rows:
            if str(row.get("split") or "") != name:
                raise SystemExit(f"REFUSED: {row.get('rowId')} in {name} declares split {row.get('split')!r}")
    check_split_isolation([*train_rows, *validation_rows])
    synthetic = [row.get("rowId") for row in [*train_rows, *validation_rows] if str(row.get("source")) == "fixture"]
    if synthetic and not args.dry_run_tiny:
        raise SystemExit(f"REFUSED: fixture rows cannot feed a real run: {synthetic[:3]}")
    if any(str(row.get("split")) == "test" for row in train_rows + validation_rows):
        raise SystemExit("REFUSED: a test row is in the train/validation input")

    # ---- seed BEFORE anything that creates parameters -------------------
    seed = int(frozen["seed"]["value"])
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    # ---------------------------------------------------------------------

    base_path = pathlib.Path(args.base)
    if args.dry_run_tiny:
        from model import build_tiny_encoder
        encoder, hidden = build_tiny_encoder()
        tokenizer = _StubTokenizer()
        base_files = {"tiny": "offline-test"}
        model_reports_mechanism = True
    else:
        if not (base_path / "config.json").exists():
            raise SystemExit(f"REFUSED: {base_path} has no config.json; the real encoder must be present on the HPC")
        encoder, hidden = build_encoder(str(base_path), unfreeze=args.arm == "unfrozen_encoder")
        tokenizer = tokenizer_from(str(base_path))
        base_files = tokenizer_files(base_path)
        model_reports_mechanism = False

    model = NextStepModel(
        encoder, hidden=hidden, n_fine=len(labels),
        dropout=float(frozen["hyper"]["dropout"]),
        freeze_encoder=args.arm == "frozen_encoder" or args.dry_run_tiny,
    )
    device = torch.device("cuda" if torch.cuda.is_available() and not args.dry_run_tiny else "cpu")
    model.to(device)

    train_examples: List[Example] = [build_example(row, labels) for row in train_rows]
    validation_examples: List[Example] = [build_example(row, labels) for row in validation_rows]
    train_actions = [action for example in train_examples for action in example.actions]
    _, fine_weights = class_weights([example.step for example in train_examples], train_actions, frozen)
    step_weights = torch.tensor(frozen["loss"]["stepWeights"], dtype=torch.float)
    lr = float(frozen["hyper"]["lrHeadFrozen"] if args.arm == "frozen_encoder" else frozen["hyper"]["lrFull"])
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=lr, weight_decay=float(frozen["hyper"]["weightDecay"]))
    tokenize = make_tokenizer_fn(tokenizer)

    epochs = args.epochs or int(frozen["hyper"]["epochsMax"])
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    best = {"epoch": 0, "score": -1.0, "path": None}
    patience = 3
    history = []
    started = time.perf_counter()
    for epoch in range(1, epochs + 1):
        train_stats = run_epoch(model, train_examples, tokenize, max_len, int(frozen["hyper"]["batch"]),
                                optimizer, step_weights, fine_weights, train=True)
        validation_stats = run_epoch(model, validation_examples, tokenize, max_len, int(frozen["hyper"]["batch"]),
                                     optimizer, step_weights, fine_weights, train=False)
        entry = {"epoch": epoch, "train": train_stats, "validation": validation_stats}
        history.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        score = validation_stats["stepAccuracy"]
        if score > best["score"]:
            best = {"epoch": epoch, "score": score, "path": out_dir / "head.pt"}
            torch.save({
                "model": {k: v for k, v in model.state_dict().items() if not k.startswith("encoder.")},
                "arm": args.arm, "epoch": epoch, "hidden": hidden,
            }, best["path"])
        elif epoch - best["epoch"] >= patience:
            print(f"early stop at epoch {epoch} (best {best['epoch']})", flush=True)
            break

    report = {
        "kind": "mechanism" if model_reports_mechanism else "training",
        "freezeId": frozen["freezeId"],
        "freezeSha256": sha256_file(FREEZE),
        "arm": args.arm,
        "seed": seed,
        "seedAppliedBeforeInit": True,
        "device": str(device),
        "deviceName": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
        "maxLen": max_len,
        "tokenLengthsSha256": sha256_file(pathlib.Path(args.token_lengths)),
        "tokenLengths": token_lengths,
        "labelDigest": labels.digest(),
        "data": {
            "train": len(train_examples), "validation": len(validation_examples),
            "trainSha256": sha256_file(pathlib.Path(args.train)),
            "validationSha256": sha256_file(pathlib.Path(args.validation)),
            "trainStepCounts": step_counts(train_rows), "validationStepCounts": step_counts(validation_rows),
            "trainObjects": object_nulls(train_rows),
        },
        "base": {"dir": str(base_path), "files": base_files},
        "headSha256": sha256_file(best["path"]) if best["path"] else None,
        "hyper": {
            "lr": lr, "batch": int(frozen["hyper"]["batch"]), "epochsRun": len(history),
            "dropout": float(frozen["hyper"]["dropout"]), "weightDecay": float(frozen["hyper"]["weightDecay"]),
            "stepWeights": frozen["loss"]["stepWeights"],
            "fineWeightsMin": float(fine_weights.min()), "fineWeightsMax": float(fine_weights.max()),
            "fineClassesAbsentFromTrain": [labels.fine[i] for i, w in enumerate(fine_weights) if float(w) == 0.0],
        },
        "bestEpoch": best["epoch"], "bestValidation": best["score"],
        "history": history,
        "wallSeconds": round(time.perf_counter() - started, 1),
        "trainedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"report -> {report_path}")
    return 0


class _StubTokenizer:
    """Deterministic offline tokenizer for the CPU mechanism test only."""

    def __call__(self, texts, padding=True, truncation=False, return_tensors="pt", max_length=None):
        ids = []
        for text in texts:
            row = [1] + [(ord(ch) % 250) + 2 for ch in str(text)] + [2]
            ids.append(row)
        width = max(len(row) for row in ids) if ids else 1
        input_ids = torch.zeros((len(ids), width), dtype=torch.long)
        mask = torch.zeros((len(ids), width), dtype=torch.long)
        for index, row in enumerate(ids):
            input_ids[index, :len(row)] = torch.tensor(row)
            mask[index, :len(row)] = 1
        return {"input_ids": input_ids, "attention_mask": mask}


if __name__ == "__main__":
    sys.exit(main())
