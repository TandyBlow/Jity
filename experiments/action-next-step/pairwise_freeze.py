"""Freeze the pairwise experiment before any training run.

Registers: base model files, the serializer source + digest, the row file and
its sha256, the label file, the split file, the group order, the length rule and
the loss/optimiser/metric definitions. `--verify` refuses to start when any
registered source changed.

    python pairwise_freeze.py --rows <train13-full-candidates.jsonl> \\
        --labels <labels-v1.json> --split <01-goal-split-v1.json> \\
        --base D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot \\
        --out freeze_pairwise.json [--rev <note>] [--verify]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pairwise_serialize as ps

FREEZE_VERSION = "action-pairwise-freeze-v1"
BASE_FILES = ("config.json", "vocab.txt", "pytorch_model.bin")


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def build(rows: Path, labels: Path, split: Path, base: Path, measurement: Path | None) -> Dict[str, Any]:
    base_files = {}
    for name in BASE_FILES:
        path = base / name
        if not path.exists():
            raise SystemExit(f"REFUSED: base file missing: {path}")
        base_files[name] = sha256_file(path)
    config = json.loads((base / "config.json").read_text(encoding="utf-8"))
    frozen: Dict[str, Any] = {
        "version": FREEZE_VERSION,
        "createdAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "base": {"dir": str(base.resolve()), "files": base_files,
                 "maxPositionEmbeddings": config.get("max_position_embeddings"),
                 "hiddenSize": config.get("hidden_size")},
        "serializer": {
            "file": "pairwise_serialize.py",
            "sha256": sha256_file(ps.SERIALIZER_PATH),
            "digest": ps.serializer_digest(),
            "format": ps.VERSION,
            "groups": ps.ALL_GROUPS,
            "skipIndex": ps.SKIP_INDEX,
            "goalChars": ps.GOAL_CHARS,
            "recentChars": ps.RECENT_CHARS,
            "presentLimit": ps.PRESENT_LIMIT,
            "itemLimit": ps.ITEM_LIMIT,
        },
        "data": {
            "rows": {"path": str(rows.resolve()), "sha256": sha256_file(rows)},
            "labels": {"path": str(labels.resolve()), "sha256": sha256_file(labels)},
            "split": {"path": str(split.resolve()), "sha256": sha256_file(split)},
        },
        "training": {
            "loss": "BCEWithLogitsLoss(pos_weight=12, reduction=sum) / (decisions * 13)",
            "posWeight": 12,
            "negativesPerDecision": 12,
            "normalisation": "per original decision (13 pairs)",
            "batchDecisions": 8,
            "epochsMax": 12,
            "earlyStopPatience": 3,
            "lrHead": 1e-3,
            "lrEncoder": 1e-5,
            "weightDecay": 0.01,
            "warmupRatio": 0.1,
            "dropout": 0.1,
            "pooling": "masked mean over tokens",
            "optimizer": "AdamW",
            "seed": 20261111,
            "seedRule": "set before encoder load and head init",
            "maxLenRule": "ceil32(p100 over train+validation inputs), cap 512, over-cap rows refused",
            "maxLenHardCap": 512,
            "truncation": "never",
            "keepGoals": "all unfinished goals (up to 6 in this data), never top-5",
        },
        "evaluation": {
            "primary": "13-way argmax",
            "rowHit": "step-1 argmax equals the labelled group",
            "skipMetrics": "skipPrecision / skipRecall with skip = 不动",
            "perGroupF1": "13 groups, worst 3 reported",
            "step2": "reported separately, never merged into the sample count",
            "testUse": "once, after the configuration is frozen",
        },
        "conflicts": "reported by measure_pairwise.py; training must not start while a"
                     " conflicting-label context remains unresolved",
        "measurement": None,
    }
    if measurement and measurement.exists():
        payload = json.loads(measurement.read_text(encoding="utf-8"))
        frozen["measurement"] = {
            "path": str(measurement.resolve()),
            "sha256": sha256_file(measurement),
            "maxLenCeil32": payload.get("maxLenCeil32"),
            "tokens": payload.get("tokens"),
            "conflictingLabelContexts": len(payload.get("conflictingLabelContexts") or []),
        }
    return frozen


def verify(frozen_path: Path) -> List[str]:
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    problems: List[str] = []
    serializer = frozen.get("serializer") or {}
    if sha256_file(ps.SERIALIZER_PATH) != serializer.get("sha256"):
        problems.append("serializer source changed")
    if ps.serializer_digest() != serializer.get("digest"):
        problems.append("serializer digest changed")
    for section, key in (("data", "rows"), ("data", "labels"), ("data", "split")):
        entry = (frozen.get(section) or {}).get(key) or {}
        path = Path(entry.get("path", ""))
        if not path.exists():
            problems.append(f"{section}.{key} missing: {path}")
        elif sha256_file(path) != entry.get("sha256"):
            problems.append(f"{section}.{key} changed: {path}")
    for name, digest in ((frozen.get("base") or {}).get("files") or {}).items():
        path = Path((frozen.get("base") or {}).get("dir", "")) / name
        if not path.exists() or sha256_file(path) != digest:
            problems.append(f"base file changed: {path}")
    measurement = frozen.get("measurement") or {}
    if measurement.get("path"):
        path = Path(measurement["path"])
        if not path.exists() or sha256_file(path) != measurement.get("sha256"):
            problems.append(f"measurement changed: {path}")
    return problems


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows")
    parser.add_argument("--labels")
    parser.add_argument("--split")
    parser.add_argument("--base")
    parser.add_argument("--measurement")
    parser.add_argument("--out")
    parser.add_argument("--rev")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)

    if args.verify:
        if not args.out:
            raise SystemExit("--verify needs --out <freeze.json>")
        problems = verify(Path(args.out))
        if problems:
            print("REFUSED: registered source changed after the freeze:")
            for problem in problems:
                print(" -", problem)
            return 2
        print("freeze verified:", args.out)
        return 0

    missing = [flag for flag, value in (("--rows", args.rows), ("--labels", args.labels),
                                        ("--split", args.split), ("--base", args.base),
                                        ("--out", args.out)) if not value]
    if missing:
        raise SystemExit(f"missing {', '.join(missing)}")
    out = Path(args.out)
    if out.exists() and not args.rev:
        raise SystemExit(f"REFUSED: {out} exists; pass --rev \"what changed\" to write a new revision")
    frozen = build(Path(args.rows), Path(args.labels), Path(args.split), Path(args.base),
                   Path(args.measurement) if args.measurement else None)
    revisions: List[Dict[str, Any]] = []
    if out.exists():
        previous = json.loads(out.read_text(encoding="utf-8"))
        revisions = previous.get("revisions") or []
        frozen["revisions"] = revisions + [{
            "at": previous.get("createdAt"),
            "note": args.rev,
            "previousSerializerDigest": (previous.get("serializer") or {}).get("digest"),
        }]
    out.write_text(json.dumps(frozen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "serializerDigest": frozen["serializer"]["digest"],
                      "rowsSha256": frozen["data"]["rows"]["sha256"],
                      "maxLen": (frozen.get("measurement") or {}).get("maxLenCeil32")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
