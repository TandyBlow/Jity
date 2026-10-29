# Freeze the N4 holdout acceptance setup (round 14).
#
# Run AFTER build_holdout.py and BEFORE the one-shot acceptance eval. The
# manifest pins the holdout file, the frozen checkpoint (r3-direction), the
# shared renderer, the judge (corpus_check), the training corpus and the
# decode settings. The acceptance eval re-checks these hashes and refuses to
# run on a mismatch, so a post-hoc edit to any frozen piece is visible.
#
# The holdout is one-shot: do not regenerate it or tune on its model outputs.
#
# Usage: python experiments/world-components/n4_holdout/freeze_r3.py
# Output: experiments/world-components/n4_holdout/freeze-r3-direction.json

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
CORPUS = HERE.parent / "n4_corpus"
CKPT = HERE.parent / "assets" / "n4-finetune" / "r3-direction"
BASE_MODEL = HERE.parent / "assets" / "randeng-t5-77m"
HOLDOUT = HERE / "holdout.jsonl"
AUTHORITY = HERE / "holdout-authority-report.json"
TRAIN_REPORT = REPO / "artifacts" / "world-components" / "n4-finetune-train-r3-direction.json"
OUT = HERE / "freeze-r3-direction.json"

sys.path.insert(0, str(CORPUS))
from n4_render import render_input  # noqa: E402


def sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha16(path) -> str:
    return sha_file(path)[:16]


def dir_hashes(path: pathlib.Path) -> dict:
    return {f.name: sha16(f) for f in sorted(path.iterdir()) if f.is_file()}


def rows_of(path: pathlib.Path) -> list:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def atomic_no_change(r) -> bool:
    return bool(r["plan"]) and all(e["kind"] == "no_change" for e in r["plan"])


def main() -> None:
    assert HOLDOUT.exists(), "build the holdout first"
    assert AUTHORITY.exists(), "run the holdout authority validation first"
    assert CKPT.exists(), "r3-direction checkpoint missing"
    holdout = rows_of(HOLDOUT)
    corpus = rows_of(CORPUS / "corpus.seeds.jsonl") + rows_of(CORPUS / "rewrites.jsonl")

    corpus_inputs = {render_input(r["plan"]) for r in corpus}
    holdout_inputs = {render_input(r["plan"]) for r in holdout}
    unseen = {i for i in holdout_inputs if i not in corpus_inputs}
    shared = holdout_inputs & corpus_inputs
    atomic_shared = {render_input(r["plan"]) for r in holdout
                     if atomic_no_change(r)}
    assert shared == atomic_shared, (
        f"holdout shares non-atomic inputs with the corpus: "
        f"{len(shared - atomic_shared)}")
    assert all(atomic_no_change(r) for r in holdout
               if render_input(r["plan"]) in shared)

    ckpt_hashes = dir_hashes(CKPT)
    if TRAIN_REPORT.exists():
        recorded = json.loads(TRAIN_REPORT.read_text(encoding="utf-8"))[
            "provenance"]["checkpointSha256_16"]
        assert recorded == ckpt_hashes, "checkpoint differs from the r3 train report"

    manifest = {
        "purpose": "frozen setup for the one-shot N4 independent holdout acceptance",
        "date": "2026-10-29",
        "checkpoint": {"path": str(CKPT), "sha256_16": ckpt_hashes},
        "baseModel": {"path": str(BASE_MODEL), "sha256_16": dir_hashes(BASE_MODEL)},
        "renderer": {"file": str(CORPUS / "n4_render.py"),
                     "sha256": sha_file(CORPUS / "n4_render.py")},
        "judge": {"file": str(CORPUS / "corpus_check.py"),
                  "sha256": sha_file(CORPUS / "corpus_check.py")},
        "corpus": {name: sha_file(CORPUS / name)
                   for name in ("corpus.seeds.jsonl", "rewrites.jsonl")},
        "decode": {"greedy": True, "maxNewTokens": 64, "numBeams": 1,
                   "tokenizerLegacy": False},
        "trainingReport": {"file": str(TRAIN_REPORT),
                           "sha256": sha_file(TRAIN_REPORT) if TRAIN_REPORT.exists() else None},
        "holdout": {
            "file": str(HOLDOUT),
            "sha256": sha_file(HOLDOUT),
            "authorityReport": {"file": str(AUTHORITY),
                                "sha256": sha_file(AUTHORITY)},
            "rows": len(holdout),
            "groups": len({r["sourceGroupId"] for r in holdout}),
            "distinctInputs": len(holdout_inputs),
            "unseenInputs": len(unseen),
            "sharedRegressionInputs": len(shared),
            "sharedRegression": [
                {"input": i,
                 "rows": sum(1 for r in holdout
                             if render_input(r["plan"]) == i
                             and atomic_no_change(r)),
                 "kind": "atomic omitted-time no_change (唯一渲染“无变化”)"}
                for i in shared],
        },
        "isolation": {"corpusInputs": len(corpus_inputs),
                      "nonAtomicOverlap": 0},
        "acceptanceRule": [
            "每个未见留出输入由冻结的 corpus_check.check_row 判定，verdict 必须为 pass",
            "任何 review/fail 即本次留出验收不通过；不重生、不回退、不改判据",
            "共享回归输入（原子 no_change）单列，不计入未见分母",
            "一次贪心解码（max_new_tokens=64），不因失败重试",
            "本清单哈希在验收前固定；验收脚本校验不符即中止",
        ],
        "notes": [
            "留出集只构造一次，未参与训练、两轮开发选择或判据修订",
            "参考正文仅用于 schema/校验器检查，验收只判模型输出对 plan 的忠实度",
        ],
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"holdout: {len(holdout)} rows / {len(holdout_inputs)} inputs "
          f"({len(unseen)} unseen + {len(shared)} shared regression)")
    print(f"freeze -> {OUT}")


if __name__ == "__main__":
    main()
