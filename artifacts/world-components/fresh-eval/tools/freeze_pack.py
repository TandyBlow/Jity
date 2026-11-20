"""Freeze the six candidates once, after human review passes.

Preconditions (any failure aborts the freeze):
  * every review row and every global confirmation is `通过`
  * `build_candidates_fresh.py --check` reports no drift
  * `run_projection_check.py --verify` re-runs the real projection and matches

It then writes candidates-fresh/FREEZE.json and FREEZE.md: the sha256 of every
pack file (except the freeze files themselves), the hashes of the inputs the
pack derives from, and the guard results. The frozen object is the pack as
committed; changing any of those bytes after the freeze makes the freeze test
fail, which is the point.

A later change is allowed only as a new pack version with a fresh review - it
must not overwrite this freeze.

Usage: python tools/freeze_pack.py [--tag NAME]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
REPO = OUT.parents[2]
DEST = OUT / "candidates-fresh"
SRC = OUT / "fresh/source"
FREEZE = DEST / "FREEZE.json"
FREEZE_MD = DEST / "freeze.md"
EXCLUDED = {"FREEZE.json", "freeze.md"}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str) -> int:
    print("冻结中止：" + message)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="c8-fresh-eval-pack-v3.2-freeze")
    args = parser.parse_args()

    review = json.loads((DEST / "review-results.json").read_text(encoding="utf-8"))
    bad_rows = {k: v for k, v in review["rows"].items() if v != "通过"}
    bad_global = {k: v for k, v in review["global"].items() if v != "通过"}
    if bad_rows or bad_global:
        return fail(f"核验未全部通过：{len(bad_rows)} 行、{len(bad_global)} 项整体确认不是通过")
    if len(review["rows"]) != 40 or len(review["global"]) != 4:
        return fail(f"核验行数不对：{len(review['rows'])} 行、{len(review['global'])} 项")

    check = subprocess.run([sys.executable, "-B", str(HERE / "build_candidates_fresh.py"),
                            "--check"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if check.returncode != 0:
        return fail("整包重生成校验未通过：\n" + check.stdout[-1500:])
    verify = subprocess.run([sys.executable, "-B", str(HERE / "run_projection_check.py"),
                             "--verify"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if verify.returncode != 0:
        return fail("投影实测复跑未通过：\n" + verify.stdout[-1500:])

    files = {}
    for path in sorted(DEST.rglob("*")):
        if path.is_file() and path.name not in EXCLUDED:
            files[path.relative_to(DEST).as_posix()] = sha(path)
    digest = hashlib.sha256(
        "\n".join(f"{k} {v}" for k, v in sorted(files.items())).encode()).hexdigest()

    projection = json.loads((DEST / "projection-check.json").read_text(encoding="utf-8"))
    inputs = {
        "fixtureRegistration": "fresh/source/registration.json",
        "fixtureDatabase": "fresh/source/authority.sqlite3",
        "fixtureDatabaseSha256": sha(SRC / "authority.sqlite3"),
        "fixtureTemplateSha256": sha(SRC / "initial-template.json"),
        "fixtureSpecsSha256": sha(SRC / "scenario-specs.json"),
        "fixtureCasesSha256": sha(SRC / "cases.json"),
        "auditSha256": sha(OUT / "source-search/audit.json"),
        "screeningSha256": sha(HERE / "screening.py"),
        "generatorSha256": sha(HERE / "build_candidates_fresh.py"),
        "n2Module": "experiments/world-components/n2_perspective.py",
        "n2Sha256": sha(REPO / "experiments/world-components/n2_perspective.py"),
        "projectionModule": "frontend/src/lib/world-engine/runtime/committed-narration.ts",
        "projectionSha256": projection["moduleSha256"],
    }
    manifest = {
        "status": "frozen",
        "tag": args.tag,
        "packVersion": json.loads((DEST / "candidates.json").read_text(encoding="utf-8"))["packVersion"],
        "frozenBy": review["reviewer"],
        "frozenUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "review": {"file": "review-results.json", "sha256": files["review-results.json"],
                   "rows": len(review["rows"]),
                   "global": len(review["global"]),
                   "conclusions": sorted({*review["rows"].values(), *review["global"].values()})},
        "guards": {"packCheck": "0 drifted, 0 missing",
                   "projectionVerify": "ok",
                   "projectionCases": [{"id": c["id"], "accepted": c["accepted"],
                                        "leakedFactIds": c.get("leakedFactIds")}
                                       for c in projection["cases"]],
                   "projectionControls": {c["name"]: {"expected": c["expected"],
                                                      "observed": c["observed"],
                                                      "ok": c["ok"]}
                                          for c in projection["controls"]}},
        "inputs": inputs,
        "files": files,
        "packDigestSha256": digest,
        "note": ("冻结后不得修改这六个候选的任何字节。任何修改都必须作为新版本重新核验，"
                 "不能覆盖本冻结。模型一次都没有运行（modelCalls=0），"
                 "所以这里冻结的是题目与输入，不是模型成绩。"),
    }
    FREEZE.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")

    lines = [
        "# 冻结记录（一次性）", "",
        f"- 标签：`{args.tag}`",
        f"- 冻结人：{review['reviewer']}（{review['date']} 逐条核验，"
        f"{len(review['rows'])}/{len(review['rows'])} 行、{len(review['global'])}/{len(review['global'])} 项整体确认通过）",
        f"- 输入包版本：v{manifest['packVersion']}",
        f"- 整包摘要：`{digest}`", "",
        "## 冻结的是什么", "",
        "六个候选的题目、事实、模型输入、N2 判定、排除检查与投影实测；"
        "以及它们所依据的夹具、数据库、审计与依赖哈希。**没有模型输出**——"
        "冻结的是题目与输入，不是模型成绩。", "",
        "## 冻结时通过的检查", "",
        "| 检查 | 结果 |", "|---|---|",
        "| 整包重生成逐字节一致 | 0 漂移、0 缺失 |",
        "| 投影实测复跑 | 与已保存结果一致 |",
        "| 泄漏自检 | 只出现现状时不判泄漏；移动真发生时判泄漏 |",
        f"| N2 模块 | `{inputs['n2Sha256'][:16]}…` |",
        f"| 页面投影模块 | `{inputs['projectionSha256'][:16]}…` |",
        "", "## 之后不改", "",
        "这份冻结记录被测试守着：`tools/test_candidates_pack.py` 会核对包里每个文件的哈希，"
        "任何改动都会让测试失败。要改就出新版本、重新核验，不覆盖这里。", "",
    ]
    FREEZE_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"frozen": True, "tag": args.tag, "files": len(files),
                      "packDigestSha256": digest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
