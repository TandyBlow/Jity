"""Build the final, hash-checkable index for the c4 stage.

Writes:
  freeze/final-index-v2.json
  freeze/final-index-v2.sha256   (hash of the JSON itself, since a file cannot contain it)
  results/final-index-v2.md
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve()
EXP = HERE.parents[1]

STATUS = "c4 本阶段诊断完成；T1 失败；独立验收尚未开展。"

PRECEDENCE = [
    "r1 的字段口径（finishedCount 与保留数、“已穷尽”措辞）以 results/diagnostic-r1-audit-v1.md 为准",
    "T1 的因果表述以 results/candidate-t1-result-v1-audit.md 为准（原句“否掉了充分原因”不成立）",
    "其余结论以 results/c4-stage-closure-v1.md 为准",
    "所有计数以运行原文（raw.jsonl）与 analysis/candidate-analysis JSON 为准；任何摘要文档与之冲突时以原文为准",
    "盲判口径以 results/blind-design-defect-v1.md 为准（v1 判词不是严格盲判）",
    "耗时口径以 results/timing-scope-v1.md 为准（1.72/4.69 s 只是解码耗时）",
]

GROUPS = {
    "协议": [
        "comparison-protocol-v1.md",
        "comparison-protocol-v2.md",
        "comparison-protocol-v3.md",
    ],
    "冻结记录": [
        "freeze/u240-identity-v1.json",
        "freeze/evidence-inventory-v1.json",
        "freeze/failure-taxonomy-v1.json",
        "freeze/failure-classification-v1.json",
        "freeze/comparison-inputs-v1.json",
        "freeze/comparison-inputs-v2.json",
        "freeze/comparison-inputs-v3.json",
        "freeze/acceptance-registration-v1.json",
        "freeze/acceptance-registration-v2.json",
        "freeze/candidate-t1-v1.json",
        "freeze/candidate-t1-v2.json",
        "freeze/candidate-t1-outcome-v1.json",
    ],
    "环境记录（环境目录不打包）": [
        "env/requirements.lock.txt",
        "env/ENVIRONMENT.md",
    ],
    "源码与脚本": [
        "scripts/beam2.py",
        "scripts/preflight_beam2.py",
        "scripts/run_preflight.py",
        "scripts/run_diagnostic.py",
        "scripts/run_candidate.py",
        "scripts/build_comparison_manifest.py",
        "scripts/inventory_u240.py",
        "scripts/classify_cf24.py",
        "scripts/copy_upstream.py",
        "scripts/build_acceptance_set.py",
        "scripts/build_blind_pack.py",
        "scripts/build_blind_pack_r2.py",
        "scripts/analyze_diagnostic.py",
        "scripts/analyze_candidate.py",
        "scripts/freeze_candidate_t1.py",
        "scripts/freeze_candidate_t1_v2.py",
        "scripts/print_batches.py",
        "scripts/snapshots/run_diagnostic-9b4b3946.py",
        "scripts/upstream/provenance.json",
        "scripts/upstream/run_cf24_baseline.py",
        "scripts/upstream/score_cf24_baseline.py",
        "scripts/upstream/review_cf24_baseline.py",
        "scripts/upstream/check_cf24_overlap.py",
        "scripts/build_blind_pack_v2.py",
        "scripts/build_final_index.py",
        "scripts/redact_paths.py",
        "scripts/run_real_state_smoke.py",
    ],
    "预检产物": [
        "artifacts/fact-wording/preflight/preflight.json",
        "artifacts/fact-wording/preflight/runs.jsonl",
        "artifacts/fact-wording/preflight/env.json",
        "artifacts/fact-wording/preflight/p7-beam2.json",
    ],
    "脱敏与发布": [
        "REDACTION.md",
        "freeze/final-index-v1-pre-redaction.json",
    ],
    "报告与补注": [
        "README.md",
        "results/preflight-report-v1.md",
        "results/diagnostic-r1-report.md",
        "results/diagnostic-r1-audit-v1.md",
        "results/t12f2-t24f3-verification-v1.md",
        "results/extra-action-candidate-v1.md",
        "results/extra-action-candidate-v2.md",
        "results/candidate-t1-result-v1.md",
        "results/candidate-t1-result-v1-audit.md",
        "results/acceptance-registration-v1.md",
        "results/run-history-v1.md",
        "results/c4-stage-closure-v1.md",
        "results/review-findings-v1.md",
        "results/review-findings-v2.md",
        "results/real-state-n3n4-smoke-v1.md",
        "results/blind-design-defect-v1.md",
        "results/timing-scope-v1.md",
        "results/next-steps-after-review-v1.md",
        "results/acceptance-registration-v2.md",
    ],
    "cf24 失败分类产物": [
        "results/cf24-catalog-v1.json",
        "results/cf24-moved-rule-pairs-v1.json",
        "results/failure-report-v1.md",
        "review/batch-01.json",
        "review/batch-02.json",
    ],
    "真实状态冒烟": [
        "artifacts/fact-wording/real-state-smoke/20261108T180059-realstate/raw.jsonl",
        "artifacts/fact-wording/real-state-smoke/20261108T180059-realstate/run.json",
        "artifacts/fact-wording/real-state-smoke/20261108T180059-realstate/env.json",
    ],
    "索引历史": [
        "freeze/final-index-v1.json",
        "freeze/final-index-v1.sha256",
        "results/final-index-v1.md",
    ],
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def add_files(rows, group, files):
    for rel in files:
        path = EXP / rel
        if not path.exists():
            rows.append(dict(group=group, path=rel, exists=False))
            continue
        rows.append(dict(group=group, path=rel, exists=True,
                         bytes=path.stat().st_size, sha256=sha(path)))


def main() -> int:
    rows = []
    for group, files in GROUPS.items():
        add_files(rows, group, files)

    r1 = sorted((EXP / "artifacts/fact-wording/diagnostic-r1").glob("*/raw.jsonl"))[-1].parent
    r2 = sorted((EXP / "artifacts/fact-wording/diagnostic-r2-cand-t1").glob("*/raw.jsonl"))[-1].parent
    for group, base in (("r1 运行原文与判词", r1), ("T1 运行原文与判词", r2)):
        rels = ["raw.jsonl", "order.jsonl", "failures.jsonl", "run.json", "env.json"]
        if (base / "analysis.json").exists():
            rels.append("analysis.json")
        if (base / "candidate-analysis.json").exists():
            rels.append("candidate-analysis.json")
        if (base / "POSTHOC-NOTES.md").exists():
            rels.append("POSTHOC-NOTES.md")
        if (base / "runner-snapshot.py").exists():
            rels.append("runner-snapshot.py")
        rels += ["blind/index.json", "blind/map.json"]
        rels += ["blind/" + p.name for p in sorted((base / "blind").glob("batch-*.json"))]
        rels += ["blind/" + p.name for p in sorted((base / "blind").glob("judged-*.json"))]
        add_files(rows, group, [str((base / r).relative_to(EXP)).replace(chr(92), "/") for r in rels])
        if group.startswith("r1"):
            v2 = sorted((base / "blind-v2").glob("batch-*.json"))
        else:
            v2 = sorted((base / "blind-v2").glob("batch-*.json"))
        rels2 = ["blind-v2/index.json", "blind-v2/map.json"] + ["blind-v2/" + p.name for p in v2]
        add_files(rows, "盲判包 v2（未判）", [str((base / r).relative_to(EXP)).replace(chr(92), "/") for r in rels2])

    counts = {}
    for row in rows:
        counts[row["group"]] = counts.get(row["group"], 0) + 1
    missing = [r["path"] for r in rows if not r["exists"]]

    payload = dict(
        protocol="c4-final-index-v2",
        status=STATUS,
        generatedAt="2026-11-09",
        root="experiments/world-components/parallel/fact_wording/",
        counts=counts,
        missing=missing,
        precedence=PRECEDENCE,
        notPackaged=dict(
            directory="env/",
            reason="runtime environment (~5 GB) is not packaged; the dependency lock and the environment note are indexed instead",
            rebuild="see env/ENVIRONMENT.md",
        ),
        redaction=dict(
            note="published copy: local absolute paths replaced by <repo>; see REDACTION.md",
            preRedactionIndex="freeze/final-index-v1-pre-redaction.json",
            preRedactionIndexSha256="503b17a6b0819b15fdd42a4455fad8d804a8ca8307ee5dd2bfbf743578f9d9ba",
            knownCrossHashBreaks=["diagnostic-r1/*/run.json manifestSha256", "preflight/preflight.json manifestSha256"],
        ),
        workflow=dict(
            r1="85 units x 2 arms, protocol v3; v1 pack was pair-adjacent (not strictly blind); blind-v2 pack unjudged",
            t1="85 units greedy only, candidate frozen in freeze/candidate-t1-v2.json; v1 pack showed the requirement clause",
            acceptance="17 units in v2 registration (provenance fixed); still never run",
        ),
        reviewState=dict(
            findings="results/review-findings-v1.md",
            packDefect="results/blind-design-defect-v1.md",
            timingScope="results/timing-scope-v1.md",
            nextSteps="results/next-steps-after-review-v1.md",
            round2="results/review-findings-v2.md",
        ),
        exclusions=[
            "freeze/final-index-v2.json", "freeze/final-index-v2.sha256", "results/final-index-v2.md",
            ".gitattributes", ".gitignore", "__pycache__/ (removed)",
        ],
        files=rows,
    )
    out_json = EXP / "freeze/final-index-v2.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    index_sha = sha(out_json)
    (EXP / "freeze/final-index-v2.sha256").write_text(index_sha + "  final-index-v2.json\n", encoding="utf-8")

    lines = [
        "# 最终索引 v2（可核查）",
        "",
        f"> 状态：{STATUS}",
        "> 根目录：`experiments/world-components/parallel/fact_wording/`",
        f"> 索引 JSON：`freeze/final-index-v2.json`，sha256 `{index_sha}`（同值见 `freeze/final-index-v2.sha256`）",
        "> 环境目录不打包：只索引 `env/requirements.lock.txt` 与 `env/ENVIRONMENT.md`。",
        "> 任务说明 `TASK.md` 位于本任务的独占目录之外（工作树根），不纳入本索引。",
        "",
        "## 冲突时采用哪份",
        "",
    ] + [f"- {x}" for x in PRECEDENCE] + [
        "",
        "## 文件与完整哈希",
        "",
        "| 组 | 路径 | 字节 | sha256 |",
        "|---|---|---|---|",
    ]
    for row in rows:
        if not row["exists"]:
            lines.append(f'| {row["group"]} | `{row["path"]}` | — | **缺失** |')
        else:
            lines.append(f'| {row["group"]} | `{row["path"]}` | {row["bytes"]:,} | `{row["sha256"]}` |')
    lines += ["", f"缺失文件：{missing if missing else '无'}", ""]
    (EXP / "results/final-index-v2.md").write_text(chr(10).join(lines), encoding="utf-8")
    print(f"indexed {len(rows)} files, missing {len(missing)}")
    print("index sha256:", index_sha)
    print("counts:", json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
