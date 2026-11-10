# -*- coding: utf-8 -*-
"""Freeze the v2 acceptance criteria for the next (model) round.

The criteria file is generated, not hand-typed, so the rule list, the code
names and the hashes of the checker and the probe set cannot drift apart.

Usage:
    python -X utf8 build_criteria.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import text_conformance as tc

HERE = Path(__file__).resolve().parent
import sys

# Default target is derived from the checker version, so running this without
# --out can never rewrite an older frozen file (criteria-v2 belongs to R2).
_default_major = tc.CONTRACT_VERSION.rsplit("v", 1)[-1]
OUT = (Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv
       else HERE / "freeze" / f"criteria-v{_default_major}.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


HARD_RULES = [
    ("fact-omitted", "每条选中事实必须能在某个句子里辨认（3-gram 召回 ≥ 0.5）"),
    ("fact-repeated", "同一条事实不能出现在多于一个句子里"),
    ("group-split", "同一组的相邻事实必须在同一句"),
    ("groups-merged", "相邻两组交界的两条事实必须在不同句"),
    ("within-group-order", "组内事实的字符位置必须按计划顺序递增"),
    ("group-out-of-order", "各组在正文中出现的句子序号必须按计划顺序递增"),
    ("added-sentence", "句子数不能多于组数"),
    ("sentence-count-mismatch", "句子数不能少于组数"),
    ("ref-name-missing", "ref=name 的句子必须出现该实体姓名"),
    ("ref-missing-antecedent", "ref=omit 的句子必须能在同句找到前置姓名"),
    ("ref-not-omitted", "ref=omit 时姓名不能紧贴在事实文本前重复出现"),
    ("ref-first-mention-omit", "首次出现不能省略"),
    ("ref-ambiguous-omit", "省略时最近一个姓名必须是同一实体"),
    ("edge-endpoints-share-sentence", "边的两端必须在不同句"),
    ("sequence-wording-missing", "required 边的目标句必须出现“随后”"),
    ("sequence-wording-outside-scope", "“随后”只能出现在 required 边的目标句里"),
    ("sequence-wording-after-fact", "“随后”必须在目标事实之前"),
    ("sequence-wording-excess", "“随后”出现次数不能多于 required 边数"),
    ("invented-sequence", "没有授权边时不得出现任何顺序词"),
    ("invented-simultaneity", "不得出现“同时/与此同时”"),
    ("invented-causality", "不得出现“因为/所以/因此/导致/于是”"),
    ("invented-pronoun", "不得出现“他/她”"),
]

REVIEW_RULES = [
    ("added-content-outside-vocabulary",
     "正文去掉姓名、事实文本、连接词、标点与功能字后剩下的内容里，有字符不在选中事实、实体名、场景可见清单中"),
    ("added-content-visible-only",
     "剩余内容只用到场景可见清单里的字词，没有事实支撑；可能是合法描写，也可能是新事件"),
]


def main() -> int:
    probe_path = HERE / "freeze" / "tamper-probes.json"
    doc = {
        "protocol": f"c3-acceptance-criteria-{tc.CONTRACT_VERSION}",
        "created": datetime.now(timezone.utc).isoformat(),
        "supersedes": ("runs/r1 (v1 checker) and runs/r2 (v2 checker). runs/r2 keeps its own "
                       "criteria-v2 record; this file governs runs/r4 onward."),
        "checker": {
            "module": "text_conformance.py",
            "sha256": sha256(HERE / "text_conformance.py"),
            "contractVersion": tc.CONTRACT_VERSION,
        },
        "probeSet": {
            "file": "freeze/tamper-probes.json",
            "sha256": sha256(probe_path),
            "probes": len(json.loads(probe_path.read_text(encoding="utf-8"))["probes"]),
        },
        "severities": {
            "hard": "位置/结构可判定；出现即判该条不合格，不允许人工改判",
            "review": "语义可判定性不足；必须有人工结论才能算通过，未填结论不等於通过",
        },
        "hardRules": [{"code": c, "rule": r} for c, r in HARD_RULES],
        "reviewRules": [{"code": c, "rule": r} for c, r in REVIEW_RULES],
        "acceptance": {
            "itemAccepted": "该条没有任何 hard 发现，且所有 review 发现都有人工结论（结论为“合法改写”才算通过）",
            "pairedSuccess": "同一来源的两份计划都被 itemAccepted",
            "gate": ("门线由留出包冻结时写入的 gateRule 决定：max(8, ceil(0.8*N))，"
                     "必须使用全部 N 个来源，不允许挑选子集；当前 holdout-a-v1 为 12 源，"
                     "即 10/12。此文件不再写死 8/10。"),
            "mustNot": [
                "不得只报告平均分而隐藏逐条 hard 发现",
                "不得用固定策略的成绩替代模型成绩",
                "不得在看过留出结果后改判据",
            ],
        },
        "manualReview": {
            "maxRowsPerBatch": 10,
            "queueFile": "runs/r4/manual-review.json",
            "fields": ["queueId", "code", "run", "outsideVocabulary", "text", "verdict", "reviewerNote"],
            "verdictValues": ["paraphrase-ok", "new-content-fail", "unsure"],
            "rule": "unsure 不计入通过；每批重新开表，不复用上一批结论",
        },
        "nextRoundPreregistration": {
            "inputs": "runs/r4/downstream-inputs.jsonl 的 18 条（与 r1/r2 逐字节一致）",
            "checker": "text_conformance.py 的 v3，代码哈希见 checker.sha256",
            "controls": ["split-all", "merge-all-adjacent", "merge-first-pair", "merge-last-pair"],
            "responsiveness": "同一来源交换 P1/P2 标签后，输出必须跟着换；否则先判“没读计划”",
            "stop": "模型成对成功不高于固定策略即停止，不加步数、不换基座",
            "holdout": "本轮 9 个来源只用于协议与工具验证，不能作为能力结论的留出",
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  checker {doc['checker']['contractVersion']} sha256 {doc['checker']['sha256'][:12]}")
    print(f"  probes {doc['probeSet']['probes']} sha256 {doc['probeSet']['sha256'][:12]}")
    print(f"  hard rules {len(HARD_RULES)}, review rules {len(REVIEW_RULES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
