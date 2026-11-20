# 跑判分器并统计误报/漏报。
#
# 四组材料：
#   positives      132 条已审目标正文（合法）      → 判 fail 即误报
#   legit_probes   528 条合法变体（省略/同义/视角内心理/场景细节）→ 判 fail 即误报
#   mutations      734 条单点改动负例             → 没判出预期规则即漏报
#   model_outputs  24 条真实输出 + 人工标注稿      → 与人工标签对照
#
# 用法：python -X utf8 run_eval.py
# 产出：artifacts/world-components/n4-narrative-eval-v1/{eval-report.json, eval-report.md}

from __future__ import annotations

import json
import pathlib

import checker

HERE = pathlib.Path(__file__).resolve().parent
BASE = HERE.parents[2] / "artifacts" / "world-components" / "n4-narrative-eval-v1"
DEV = HERE.parent / "n4_narrative_dev"


def load_jsonl(p: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_worlds() -> dict:
    return {"w_fog_harbor": json.loads((DEV / "world.json").read_text(encoding="utf-8")),
            "w_snow_pass": json.loads((DEV / "holdout_world.json").read_text(encoding="utf-8"))}


def main() -> int:
    cases = {c["caseId"]: c for c in load_jsonl(BASE / "cases.jsonl")}
    worlds = load_worlds()
    report: dict = {"materials": {}, "results": {}}

    # ---- positives -------------------------------------------------------
    pos = load_jsonl(BASE / "positives.jsonl")
    pos_fail, pos_unc, pos_pass = [], [], 0
    for p in pos:
        c = cases[p["caseId"]]
        r = checker.check_case(c, p["text"], worlds[c["worldId"]])
        if r["verdict"] == "fail":
            pos_fail.append({"id": p["id"], "checks": [
                x for x in r["checks"] if x["verdict"] == "fail"]})
        elif r["verdict"] == "uncertain":
            pos_unc.append({"id": p["id"],
                            "rules": sorted({x["rule"] for x in r["checks"]
                                             if x["verdict"] == "uncertain"})})
        else:
            pos_pass += 1
    report["materials"]["positives"] = len(pos)
    report["results"]["positives"] = {
        "pass": pos_pass, "uncertain": len(pos_unc), "fail": len(pos_fail),
        "falsePositives": pos_fail,
        "uncertain_rules": pos_unc[:20],
    }

    # ---- legit probes ----------------------------------------------------
    probes = load_jsonl(BASE / "legit_probes.jsonl")
    probe_fail, probe_unc, probe_pass = [], [], 0
    for p in probes:
        c = cases[p["caseId"]]
        r = checker.check_case(c, p["text"], worlds[c["worldId"]])
        if r["verdict"] == "fail":
            probe_fail.append({"id": p["id"], "probe": p["id"].split(":")[0], "checks": [
                x for x in r["checks"] if x["verdict"] == "fail"]})
        elif r["verdict"] == "uncertain":
            probe_unc.append(p["id"].split(":")[0])
        else:
            probe_pass += 1
    report["materials"]["legitProbes"] = len(probes)
    report["results"]["legitProbes"] = {
        "pass": probe_pass, "uncertain": len(probe_unc), "fail": len(probe_fail),
        "falsePositives": probe_fail[:20],
        "uncertain_byProbe": {k: probe_unc.count(k) for k in set(probe_unc)},
    }

    # ---- mutations -------------------------------------------------------
    muts = load_jsonl(BASE / "mutations.jsonl")
    per_type: dict[str, dict] = {}
    for m in muts:
        c = cases[m["caseId"]]
        r = checker.check_case(c, m["text"], worlds[c["worldId"]])
        expected = set(m["expectedRule"].split("|"))
        hit = any(x["verdict"] == "fail" and x["rule"] in expected for x in r["checks"])
        bucket = per_type.setdefault(m["mutation"], {"hit": 0, "uncertain": 0, "miss": 0,
                                                     "examples": []})
        if hit:
            bucket["hit"] += 1
        elif r["verdict"] == "uncertain":
            bucket["uncertain"] += 1
            if len(bucket["examples"]) < 2:
                bucket["examples"].append(
                    {"id": m["id"], "why": [x for x in r["checks"]
                                            if x["verdict"] == "uncertain"][:2]})
        else:
            bucket["miss"] += 1
            if len(bucket["examples"]) < 2:
                bucket["examples"].append(
                    {"id": m["id"], "why": [x for x in r["checks"]
                                            if x["verdict"] != "pass"][:2]})
    report["materials"]["mutations"] = len(muts)
    report["results"]["mutations"] = per_type

    # ---- model outputs vs annotations -----------------------------------
    ann = {a["id"]: a for a in load_jsonl(BASE / "annotations.jsonl")}
    outs = load_jsonl(BASE / "model_outputs.jsonl")
    rows = []
    conf = {"fp": [], "fn": [], "agree": 0, "abstain": [],
            "missedUncertain": [], "matrix": {
                "humanPass": {"checkerPass": 0, "checkerUncertain": 0, "checkerFail": 0},
                "humanUncertain": {"checkerPass": 0, "checkerUncertain": 0, "checkerFail": 0},
                "humanFail": {"checkerPass": 0, "checkerUncertain": 0, "checkerFail": 0},
            }}
    for o in outs:
        c = cases[o["caseId"]]
        r = checker.check_case(c, o["text"], worlds[c["worldId"]])
        a = ann.get(o["id"])
        human = a["overall"] if a else None
        row = {"id": o["id"], "checker": r["verdict"], "human": human,
               "checkerFails": [x for x in r["checks"] if x["verdict"] == "fail"],
               "humanReasons": a["reasons"] if a else []}
        rows.append(row)
        if human is None:
            continue
        key = {"pass": "humanPass", "uncertain": "humanUncertain",
               "fail": "humanFail"}[human]
        cell = {"pass": "checkerPass", "uncertain": "checkerUncertain",
                "fail": "checkerFail"}[r["verdict"]]
        conf["matrix"][key][cell] += 1
        if r["verdict"] == "fail" and human == "pass":
            conf["fp"].append(row)
        elif r["verdict"] == "pass" and human == "fail":
            conf["fn"].append(row)          # 严格漏报：人说错、机器说对
        elif r["verdict"] == "pass" and human == "uncertain":
            conf["missedUncertain"].append(row)  # 人说存疑、机器直接放行
        elif r["verdict"] == "uncertain":
            conf["abstain"].append(row)
        elif r["verdict"] == human:
            conf["agree"] += 1
    report["materials"]["modelOutputs"] = len(outs)
    report["results"]["modelOutputs"] = {
        "rows": rows,
        "confusion": {
            "agree": conf["agree"],
            "falsePositive": len(conf["fp"]),
            "falseNegative": len(conf["fn"]),
            "missedUncertain": len(conf["missedUncertain"]),
            "abstain": len(conf["abstain"]),
            "matrix": conf["matrix"],
        },
        "falsePositiveDetail": conf["fp"],
        "falseNegativeDetail": conf["fn"],
        "missedUncertainDetail": [{"id": x["id"], "human": x["human"]}
                                  for x in conf["missedUncertain"]],
        "abstainDetail": [{"id": x["id"], "human": x["human"],
                           "checker": x["checker"]} for x in conf["abstain"]],
        "note": "人工标签为 assistant-draft（待人工复核）；这里只比较机器与草稿标签，"
                "不能当作判分器已通过验收",
    }

    # ---- summary ---------------------------------------------------------
    mut_total = sum(v["hit"] + v["uncertain"] + v["miss"] for v in per_type.values())
    mut_hit = sum(v["hit"] for v in per_type.values())
    report["summary"] = {
        "positives_falsePositiveRate": f"{len(pos_fail)}/{len(pos)}",
        "legitProbes_falsePositiveRate": f"{len(probe_fail)}/{len(probes)}",
        "mutations_detected": f"{mut_hit}/{mut_total}",
        "modelOutputs_agreement": f"{conf['agree']}/{len(rows)}",
        "verdict_ofJudge": "未通过人工复核：标签是草稿，误报/漏报数字只能说明当前规则状态",
    }

    (BASE / "eval-report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = ["# 叙事判分器 v1 评测报告（自动生成）", "",
             f"- 正例（已审目标正文）：{report['summary']['positives_falsePositiveRate']} 被误判 fail；"
             f"uncertain {len(pos_unc)}",
             f"- 合法变体：{report['summary']['legitProbes_falsePositiveRate']} 被误判 fail；"
             f"uncertain {len(probe_unc)}",
             f"- 单点负例：{report['summary']['mutations_detected']} 按预期规则判出",
             f"- 真实输出对照草稿标注：{report['summary']['modelOutputs_agreement']} 一致，"
             f"误报 {len(conf['fp'])}，严格漏报 {len(conf['fn'])}，"
             f"人工存疑但机器放行 {len(conf['missedUncertain'])}，"
             f"abstain {len(conf['abstain'])}",
             f"  矩阵（行=人工，列=机器）：{json.dumps(conf['matrix'], ensure_ascii=False)}",
             ""]
    for k, v in sorted(per_type.items()):
        total = v["hit"] + v["uncertain"] + v["miss"]
        lines.append(f"- {k}: 判出 {v['hit']}/{total}，uncertain {v['uncertain']}，漏 {v['miss']}")
    (BASE / "eval-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
