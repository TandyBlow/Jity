"""Prepare D review identities and reconcile human claims; never grant approval.

Only D drafts and the two registered rule sources are read as content. B/C
sources are checked through Git object metadata only, never sample bodies.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from lab import _parse_json, canonical_bytes, guard_case, load_jsonl, sha256_file, validate_dataset

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / "data"
RULE_PATHS = {"design/browser-world-state-workflow.md",
              "design/world-engine-reports/components-logic/evaluation-plan.md"}
PROTECTED = [
    ("B", "90463b12eac989d4bd3c3bb8b3e2e54720177195", "artifacts", "58e04d7ed2f27133c13a6c446eec600d87d447b7", "tree"),
    ("B", "90463b12eac989d4bd3c3bb8b3e2e54720177195", "frontend/src/lib/world-engine", "7d9a7edfff713858357da6bd36bb120b75d14a4f", "tree"),
    ("B", "90463b12eac989d4bd3c3bb8b3e2e54720177195", "frontend/src/lib/world-engine/runtime/b3-samples.ts", "c7c11bf2d6aa42b21e2b91f9722fc8bdd3d63914", "blob"),
    ("B", "90463b12eac989d4bd3c3bb8b3e2e54720177195", "frontend/src/lib/world-engine/runtime/b3-short-samples.ts", "48de5aac7aea468b46678cc3e7b6243047490a96", "blob"),
    ("C", "30069354cc061be94fc31c897dada0f641ed3f90", "experiments/world-components", "58efd205a733c47448770d50cff13f953a07d318", "tree"),
    ("C", "30069354cc061be94fc31c897dada0f641ed3f90", "artifacts/world-components", "dda61b65d3c8bd955f1ddd3bfdfc9155ad97bf07", "tree"),
    ("C", "30069354cc061be94fc31c897dada0f641ed3f90", "experiments/world-components/n4_holdout/holdout.jsonl", "31ebca6690407634352b5ff277a0f2109300dced", "blob"),
    ("C", "30069354cc061be94fc31c897dada0f641ed3f90", "experiments/world-components/n4_holdout/freeze-r3-direction.json", "fe079c0eb8e458edd59a2cecc4dd3496843135c2", "blob"),
]


def sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_packet():
    inputs = load_jsonl(DATA / "dev-inputs.jsonl")
    reviews = load_jsonl(DATA / "dev-review-drafts.jsonl")
    report = validate_dataset(inputs, reviews)
    if not report["valid"]:
        raise ValueError(report["problems"])
    by_id = {r["caseId"]: r for r in reviews}
    return {"schema": "jity-d-human-review-packet-v1",
            "inputSha256": sha256_file(DATA / "dev-inputs.jsonl"),
            "reviewDraftSha256": sha256_file(DATA / "dev-review-drafts.jsonl"),
            "provenanceSha256": sha256_file(DATA / "dev-provenance.json"),
            "cases": [{**c, "inputSha256": sha(c["input"]), "reviewSha256": sha(by_id[c["caseId"]]),
                       "review": by_id[c["caseId"]], "guard": guard_case(c)} for c in inputs]}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("时间必须是带时区的 ISO 字符串")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("时间缺少时区")


def reconcile_claims(claims, packet):
    """Check identities, retaining partial/revise/uncertain decisions verbatim.

    A matching file is still an unauthenticated human claim. This function does
    not edit original labels, prove reviewer identity, or open model/data gates.
    """
    if not isinstance(claims, dict) or claims.get("schema") != "jity-d-user-review-claims-v1":
        raise ValueError("不是本批支持的审阅导出格式")
    if not isinstance(claims.get("reviewer"), str) or not claims["reviewer"].strip():
        raise ValueError("导出缺少审阅者称呼")
    timestamp(claims.get("exportedAt"))
    if claims.get("formalEvaluationAllowed") is not False or claims.get("verificationStatus") != "unverified_export_pending_reconciliation":
        raise ValueError("导出不能自授审批或正式评测权限")
    for key, expected in (("inputFileSha256", packet["inputSha256"]),
                          ("reviewDraftFileSha256", packet["reviewDraftSha256"])):
        if claims.get(key) != expected:
            raise ValueError(f"批次不匹配：{key}")
    # All three files define this review batch. A missing provenance binding
    # cannot be treated as an identity match, including in older exports.
    if claims.get("provenanceFileSha256") != packet["provenanceSha256"]:
        raise ValueError("来源登记版本缺失或不匹配")
    cases = {c["caseId"]: c for c in packet["cases"]}
    decisions = claims.get("decisions")
    if not isinstance(decisions, list) or not 1 <= len(decisions) <= len(cases):
        raise ValueError("审阅记录必须是非空列表，且不能多于题目数")
    seen, counts = set(), Counter()
    for item in decisions:
        if not isinstance(item, dict) or not isinstance(item.get("caseId"), str):
            raise ValueError("审阅记录缺少有效题号")
        case_id = item["caseId"]
        if case_id in seen or case_id not in cases:
            raise ValueError(f"重复或未知题号：{case_id}")
        seen.add(case_id)
        case = cases[case_id]
        for key, expected in (("sourceGroup", case["sourceGroup"]),
                              ("inputSha256", case["inputSha256"]),
                              ("reviewDraftSha256", case["reviewSha256"])):
            if item.get(key) != expected:
                raise ValueError(f"题目身份不匹配：{case_id}/{key}")
        decision, note = item.get("decision"), item.get("note")
        if decision not in ("agree", "revise", "uncertain") or not isinstance(note, str):
            raise ValueError(f"无效意见：{case_id}")
        if decision == "revise" and not note.strip():
            raise ValueError(f"修改意见缺少原因：{case_id}")
        timestamp(item.get("recordedAt"))
        counts[decision] += 1
    return {"schema": "jity-d-review-reconciliation-v1",
            "status": "identity_matched_claims_pending_human_confirmation",
            "reviewerClaim": claims["reviewer"], "inputFileSha256": packet["inputSha256"],
            "reviewDraftFileSha256": packet["reviewDraftSha256"],
            "summary": {"total": len(cases), "recorded": len(seen), "missing": len(cases)-len(seen),
                        **{name: counts[name] for name in ("agree", "revise", "uncertain")}},
            "missingCaseIds": sorted(set(cases)-seen), "claims": claims,
            "reviewerIdentityAuthenticated": False, "humanSemanticApproval": False,
            "sourceIndependence": "unverified", "formalEvaluationAllowed": False,
            "modelExecutionAuthorized": False}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=20)


def audit_sources():
    packet = build_packet()
    provenance = _parse_json((DATA / "dev-provenance.json").read_text(encoding="utf-8"))
    checks, problems = [], []
    for name, identity in provenance["files"].items():
        path = DATA / name if name.endswith((".jsonl", ".json")) else DATA.parent / name
        if name not in {"dev-inputs.jsonl", "dev-review-drafts.jsonl", "generate_dev_drafts.py"}:
            raise ValueError("来源登记出现未允许的内容路径")
        ok = sha256_file(path) == identity["sha256"]
        checks.append({"kind": "D-file-sha256", "path": str(path.relative_to(ROOT)), "matched": ok})
        if not ok:
            problems.append(f"D 文件哈希不匹配：{name}")
    for basis in provenance["sourceBasis"]:
        if basis["path"] not in RULE_PATHS or not re.fullmatch(r"[0-9a-f]{40}", basis["commit"]):
            raise ValueError("只读取登记的原设计/协议，不读取保护样本正文")
        key = basis["commit"] + ":" + basis["path"]
        blob = git("rev-parse", key).decode().strip()
        content_sha = hashlib.sha256(git("show", key)).hexdigest()
        ok = blob == basis["gitBlobSha1"] and content_sha == basis["sha256"]
        checks.append({"kind": "pinned-rule-source", "commit": basis["commit"], "path": basis["path"],
                       "gitBlobSha1": blob, "sha256": content_sha, "matched": ok})
        if not ok:
            problems.append(f"规则来源身份不匹配：{basis['path']}")
    groups = {g["sourceGroup"]: g for g in provenance["sourceGroups"]}
    records = {r["caseId"]: r for r in provenance["cases"]}
    if len(groups) != 40 or len(records) != 42 or len(provenance["sourceGroups"]) != 40 or len(provenance["cases"]) != 42:
        problems.append("来源组/题目登记数量不符")
    expected_groups = {}
    for case in packet["cases"]:
        expected_groups.setdefault(case["sourceGroup"], []).append(case["caseId"])
    if {key: sorted(g["caseIds"]) for key, g in groups.items()} != {key: sorted(ids) for key, ids in expected_groups.items()}:
        problems.append("来源组与题目列表不完全一致")
    for case in packet["cases"]:
        record = records.get(case["caseId"], {})
        raw_case = {k: v for k, v in case.items() if k not in {"inputSha256", "reviewSha256", "review", "guard"}}
        if (case["caseId"] not in groups.get(case["sourceGroup"], {}).get("caseIds", [])
                or record.get("sourceGroup") != case["sourceGroup"]
                or record.get("rawCanonicalRowSha256") != sha(raw_case)
                or record.get("modelVisibleInputSha256") != case["inputSha256"]
                or record.get("reviewDraftSha256") != case["reviewSha256"]):
            problems.append(f"逐题登记不匹配：{case['caseId']}")
    protected = []
    for owner, commit, path, expected, kind in PROTECTED:
        try:
            actual = git("rev-parse", commit + ":" + path).decode().strip()
            object_type = git("cat-file", "-t", actual).decode().strip()
            matched = actual == expected and object_type == kind
            status = "anchor_identity_matched" if matched else "anchor_identity_mismatch"
        except subprocess.SubprocessError:
            actual, object_type, status = None, None, "anchor_unavailable"
        protected.append({"owner": owner, "commit": commit, "path": path,
                          "expectedGitObject": expected, "observedGitObject": actual,
                          "objectType": object_type, "status": status, "sampleBodyRead": False})
    return {"schema": "jity-d-source-review-preparation-v1",
            "preparedAt": datetime.now(timezone.utc).isoformat(), "DCommit": git("rev-parse", "HEAD").decode().strip(),
            "auditTool": {"path": str(Path(__file__).resolve().relative_to(ROOT)), "sha256": sha256_file(__file__)},
            "inputSha256": packet["inputSha256"], "reviewDraftSha256": packet["reviewDraftSha256"],
            "provenanceSha256": packet["provenanceSha256"], "caseCount": 42, "sourceGroupCount": 40,
            "identityChecks": checks, "perCaseIdentityChecks": len(packet["cases"]),
            "DIdentityProblems": problems,
            "DIdentityStatus": "matched" if not problems else "mismatch",
            "protectedAnchors": protected,
            "humanReview": "pending-user", "secondHumanReview": "unassigned", "adjudicator": "unassigned",
            "protectedSourceCompleteness": "unverified", "contentDeduplication": "unverified",
            "semanticSourceIndependence": "unverified", "formalEvaluationAllowed": False,
            "modelExecutionAuthorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    reconciliation = commands.add_parser("reconcile", help="核对导出声明，不改标签、不审批")
    reconciliation.add_argument("file", type=Path)
    audit = commands.add_parser("audit-sources", help="只核对 D 身份与 B/C Git 元数据")
    for command in (reconciliation, audit):
        command.add_argument("--out", type=Path, help="独占新建结果文件；拒绝覆盖既有记录")
    args = parser.parse_args()
    try:
        if args.command == "reconcile":
            raw = args.file.read_bytes()
            if len(raw) > 2_000_000:
                raise ValueError("审阅导出文件过大")
            result = reconcile_claims(_parse_json(raw.decode("utf-8")), build_packet())
            result["exportFileSha256"] = hashlib.sha256(raw).hexdigest()
        else:
            result = audit_sources()
        output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(output)
            print(str(args.out))
        else:
            print(output, end="")
        return 1 if result.get("DIdentityProblems") else 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"核对失败：{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
