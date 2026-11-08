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
# The current round is runs/r4 (v3 checker). runs/r2 is the v2 history: it keeps
# its own criteria-v2 pins and is never used to open today's gate.
SIGNOFF = HERE / "runs" / "r4" / "signoff.json"
ACCEPTANCE = HERE / "runs" / "r4" / "acceptance.json"
R2_SIGNOFF = HERE / "runs" / "r2" / "signoff.json"
ADOPTION = HERE / "freeze" / "checkpoint-adoption.json"
def newest_criteria() -> Path:
    found = sorted((HERE / "freeze").glob("criteria-v[0-9]*.json"))
    return found[-1] if found else HERE / "freeze" / "criteria-v2.json"


CRITERIA = newest_criteria()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


import check_adoption as adoption  # noqa: E402


def check_holdout(freeze_path: Path | None = None) -> dict:
    freeze = freeze_path or HOLDOUT_FREEZE
    if not freeze.exists():
        receipt = HERE / "runs" / "r3" / "holdout-acceptance.json"
        if receipt.exists():
            r = json.loads(receipt.read_text(encoding="utf-8"))
            gate = r.get("gate", {})
            return {"ready": False, "state": "留出待交付",
                    "detail": (f"包已收到（{r.get('receiptId')}），校验 blockedBy="
                               f"{gate.get('blockedBy')}；冻结件未生成")}
        return {"ready": False, "state": "留出待交付",
                "detail": "freeze/holdout-v1-freeze.json 不存在：A 的包未到，或未通过 --package 校验"}
    doc = json.loads(freeze.read_text(encoding="utf-8"))
    missing = []
    for key in ("package", "manifestSha256", "semanticSignoff", "pairFiles",
                "packageDigest", "gateRule", "plans", "sources"):
        if not doc.get(key):
            missing.append(key)
    if missing:
        return {"ready": False, "state": "留出冻结不完整",
                "detail": f"冻结件缺字段：{missing}"}
    if doc.get("status") != "admissible":
        return {"ready": False, "state": "留出不通过", "detail": f"status={doc.get('status')}"}

    # A frozen record is only valid while the material it froze is unchanged.
    package = Path(doc["package"])
    problems = []
    for rel, want in (doc.get("pairFiles") or {}).items():
        path = package / rel
        if not path.exists():
            problems.append(f"missing {rel}")
        elif sha256(path) != want:
            problems.append(f"changed {rel}")
    if problems:
        return {"ready": False, "state": "留出冻结件已过期",
                "detail": "冻结后材料变了：" + "；".join(problems[:4])}
    recomputed = hashlib.sha256(json.dumps(
        {rel: sha256(package / rel) for rel in (doc.get("pairFiles") or {})},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if recomputed != (doc.get("packageDigest") or {}).get("sha256"):
        return {"ready": False, "state": "留出冻结件已过期",
                "detail": "冻结件的 packageDigest 与重算值不一致"}
    # The database carries the evidence the facts were checked against, so a
    # changed or deleted world.db must also invalidate the freeze.
    manifest_path = package / "manifest.json"
    db_problems = []
    if not manifest_path.exists():
        db_problems.append("manifest.json missing")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        db_rel = (manifest.get("databases") or {})
        db_name = next(iter(db_rel.values()), "world.db") if db_rel else "world.db"
        db_path = package / db_name
        want_db = (manifest.get("files") or {}).get("world.db")
        if not db_path.exists():
            db_problems.append(f"{db_name} missing")
        elif want_db and sha256(db_path) != want_db:
            db_problems.append(f"{db_name} changed")
    if db_problems:
        return {"ready": False, "state": "留出冻结件已过期",
                "detail": "冻结后材料变了：" + "；".join(db_problems)}

    signoff = doc.get("semanticSignoff") or {}
    signoff_path = package / signoff.get("file", "")
    if not signoff_path.exists() or sha256(signoff_path) != signoff.get("sha256"):
        return {"ready": False, "state": "留出冻结件已过期",
                "detail": "语义签认文件缺失或与冻结记录不一致"}
    rule = doc["gateRule"]
    return {"ready": True, "state": "留出已冻结",
            "detail": (f"{len(doc.get('sources', []))} 源；门线 {rule.get('minimumPairedSuccess')}/"
                       f"{rule.get('sources')}（{rule.get('formula')}，冻结时预登记）；"
                       f"包摘要 {doc['packageDigest']['sha256'][:12]}")}


def check_signoff() -> dict:
    if not SIGNOFF.exists():
        detail = (f"{SIGNOFF.relative_to(HERE).as_posix()} 不存在；先填 "
                  f"{SIGNOFF.with_name('signoff-form.json').relative_to(HERE).as_posix()} "
                  f"再跑 apply_signoff.py")
        if R2_SIGNOFF.exists():
            detail += "。runs/r2/signoff.json 是 v2 检查器的历史审计记录，不用于当前门"
        return {"ready": False, "state": "人工签认待完成", "detail": detail}
    signed = json.loads(SIGNOFF.read_text(encoding="utf-8"))
    if not signed.get("signed"):
        return {"ready": False, "state": "人工签认待完成", "detail": "signoff.json 未标 signed"}
    if signed.get("satisfiesHumanSignoff") is not True:
        pins0 = signed.get("pinnedInputs") or {}
        stale0 = []
        for key, rel in (("criteria", "freeze/criteria-v2.json"),
                         ("tamperProbes", "freeze/tamper-probes.json"),
                         ("manualReview", "runs/r2/manual-review.json"),
                         ("checker", "text_conformance.py")):
            want = (pins0.get(key) or {}).get("sha256")
            fp = HERE / rel
            if want and fp.exists() and want != sha256(fp):
                stale0.append(rel)
        extra = f"；且该记录钉定的文件已变（{stale0}），更加不能当作有效签认" if stale0 else ""
        return {
            "ready": False,
            "state": "人工签认待完成",
            "detail": (f"已有签认记录，但 signerKind={signed.get('signerKind')!r}、"
                       f"signoffClass={signed.get('signoffClass')!r}：仅作审计材料，"
                       f"不满足人工签认要求；签认人 {signed.get('signer')}，{signed.get('date')}，"
                       f"审阅 {signed.get('reviewedCommit')}{extra}"),
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
    newest = sorted((HERE / "freeze").glob("criteria-v*.json"))
    criteria_path = newest[-1] if newest else CRITERIA
    criteria = json.loads(criteria_path.read_text(encoding="utf-8")) if criteria_path.exists() else {}
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
