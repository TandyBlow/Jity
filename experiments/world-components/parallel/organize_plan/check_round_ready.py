# -*- coding: utf-8 -*-
"""Are we allowed to run a model-capability experiment yet?

Three independent prerequisites, in the order they can be satisfied:

  1. holdout delivered and frozen      freeze/holdout-v1-freeze.json
  2. sign-off sealed (gate OPEN)       runs/r2/signoff.json + acceptance.json
  3. attributable checkpoint adopted   freeze/checkpoint-adoption.json

They are independent: any one can be ready while the others are not, and a
signed gate does NOT unlock the model round. Route A forensics ended with
"no attributable local checkpoint", so item 3 stays missing until someone
supplies a weight file whose sha256 can be matched against a record.

Exit code is 0 only when all three are ready; otherwise 1, and the model round
is reported as BLOCKED.

Usage:
    python -X utf8 check_round_ready.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOLDOUT_FREEZE = HERE / "freeze" / "holdout-v1-freeze.json"
SIGNOFF = HERE / "runs" / "r2" / "signoff.json"
ACCEPTANCE = HERE / "runs" / "r2" / "acceptance.json"
ADOPTION = HERE / "freeze" / "checkpoint-adoption.json"
CRITERIA = HERE / "freeze" / "criteria-v2.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


import check_adoption as adoption  # noqa: E402


def check_holdout() -> dict:
    if not HOLDOUT_FREEZE.exists():
        receipt = HERE / "runs" / "r3" / "holdout-acceptance.json"
        if receipt.exists():
            r = json.loads(receipt.read_text(encoding="utf-8"))
            gate = r.get("gate", {})
            return {"ready": False, "state": "留出待交付",
                    "detail": (f"包已收到（{r.get('receiptId')}），校验 blockedBy="
                               f"{gate.get('blockedBy')}；冻结件未生成")}
        return {"ready": False, "state": "留出待交付",
                "detail": "freeze/holdout-v1-freeze.json 不存在：A 的包未到，或未通过 --package 校验"}
    doc = json.loads(HOLDOUT_FREEZE.read_text(encoding="utf-8"))
    missing = []
    for key in ("package", "manifestSha256", "semanticReview", "plans", "sources"):
        if not doc.get(key):
            missing.append(key)
    if missing:
        return {"ready": False, "state": "留出冻结不完整",
                "detail": f"冻结件缺字段：{missing}"}
    if doc.get("status") != "admissible":
        return {"ready": False, "state": "留出不通过", "detail": f"status={doc.get('status')}"}
    return {"ready": True, "state": "留出已冻结",
            "detail": f"{len(doc.get('sources', []))} 源；manifest {doc['manifestSha256'][:12]}；"
                      f"semanticReview {doc['semanticReview']['sha256'][:12]}"}


def check_signoff() -> dict:
    if not SIGNOFF.exists():
        return {"ready": False, "state": "人工签认待完成",
                "detail": "runs/r2/signoff.json 不存在；先填 runs/r2/signoff-form.json 再跑 apply_signoff.py"}
    signed = json.loads(SIGNOFF.read_text(encoding="utf-8"))
    if not signed.get("signed"):
        return {"ready": False, "state": "人工签认待完成", "detail": "signoff.json 未标 signed"}
    if signed.get("satisfiesHumanSignoff") is not True:
        return {
            "ready": False,
            "state": "人工签认待完成",
            "detail": (f"已有签认记录，但 signerKind={signed.get('signerKind')!r}、"
                       f"signoffClass={signed.get('signoffClass')!r}：仅作审计材料，"
                       f"不满足人工签认要求；签认人 {signed.get('signer')}，{signed.get('date')}，"
                       f"审阅 {signed.get('reviewedCommit')}"),
        }
    if not ACCEPTANCE.exists():
        return {"ready": False, "state": "人工签认待完成", "detail": "acceptance.json 不存在，门状态未计算"}
    # A signed record is only valid while the things it pinned are unchanged.
    # Otherwise a later criteria/probe/review edit would silently keep the gate
    # open on inputs the signer never saw.
    pins = signed.get("pinnedInputs") or {}
    stale = []
    for key, rel in (("criteria", "freeze/criteria-v2.json"),
                     ("tamperProbes", "freeze/tamper-probes.json"),
                     ("manualReview", "runs/r2/manual-review.json"),
                     ("checker", "text_conformance.py")):
        want = (pins.get(key) or {}).get("sha256")
        path = HERE / rel
        if want and path.exists() and want != sha256(path):
            stale.append(rel)
    if stale:
        return {"ready": False, "state": "签认已过期",
                "detail": f"签认钉定的文件已改动：{stale}；需要重新生成签认表并重新签认"}

    gate = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))
    status = gate.get("gateStatus")
    detail = (f"签认人 {signed.get('signer')}（{signed.get('signerKind')}），"
              f"{signed.get('date')}，审阅 {signed.get('reviewedCommit')}；"
              f"结论 {signed.get('humanCounts')}")
    if status != "OPEN":
        return {"ready": False, "state": "人工签认已填但门未开", "detail": f"gateStatus={status}；{detail}"}
    open_items = gate.get("openItems") or []
    return {"ready": True, "state": "签认完成，门 OPEN",
            "detail": detail + (f"；未通过项 {open_items}" if open_items else "")}


def check_checkpoint() -> dict:
    if not ADOPTION.exists():
        forensics = HERE / "freeze" / "checkpoint-forensics.json"
        why = "freeze/checkpoint-adoption.json 不存在"
        if forensics.exists():
            f = json.loads(forensics.read_text(encoding="utf-8"))
            why += f"；取证结论 {f.get('verdict', {}).get('verdict')}"
        return {"ready": False, "state": "计划训练检查点缺失", "detail": why}

    # Adoption rules live in check_adoption.py: the hash must be tied to the
    # training inputs + plan format, the training run and the selection result,
    # and must not be the base-model hash.
    problems = adoption.check()
    if problems:
        return {"ready": False, "state": "检查点不可归因", "detail": "；".join(problems[:4]) +
                (f"（共 {len(problems)} 项）" if len(problems) > 4 else "")}
    doc = json.loads(ADOPTION.read_text(encoding="utf-8"))
    return {"ready": True, "state": "检查点已采纳",
            "detail": (f"{doc['modelSha256'][:12]}；planFormat={doc['trainingInputs']['planFormat'][:40]}；"
                       f"selection epoch {doc['selection']['epoch']}/{doc['selection']['updates']} updates；"
                       f"matchedField={doc['trainingRun']['recordField']}")}


def main() -> int:
    criteria = json.loads(CRITERIA.read_text(encoding="utf-8")) if CRITERIA.exists() else {}
    states = [check_holdout(), check_signoff(), check_checkpoint()]
    ready = all(s["ready"] for s in states)

    print("| # | 状态 | 就绪 | 依据 |")
    print("| --- | --- | --- | --- |")
    for i, s in enumerate(states, 1):
        print(f"| {i} | {s['state']} | {'yes' if s['ready'] else 'NO'} | {s['detail']} |")
    print()
    print(f"判据：{criteria.get('checker', {}).get('contractVersion', '?')} "
          f"{criteria.get('checker', {}).get('sha256', '')[:12]}")
    if ready:
        print("模型能力实验：可以启动（三项均就绪）")
        return 0
    blocked = [s["state"] for s in states if not s["ready"]]
    print(f"模型能力实验：BLOCKED（未就绪：{'、'.join(blocked)}）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
