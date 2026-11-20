"""Join frozen cf24 archives, classify existing findings, and expose coverage gaps.

Standard library only. Does not import torch, load a model, generate, or write
outside fact_wording. --check verifies source pins and all generated artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
TASK = HERE.parents[1]
TREE = HERE.parents[5]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def indexed(rows, label):
    result = {row["unitId"]: (i, row) for i, row in enumerate(rows)}
    require(len(result) == len(rows), f"duplicate unitId in {label}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    inventory_path = TASK / "freeze/evidence-inventory-v1.json"
    identity_path = TASK / "freeze/u240-identity-v1.json"
    taxonomy_path = TASK / "freeze/failure-taxonomy-v1.json"
    inventory, identity, taxonomy = map(read, (inventory_path, identity_path, taxonomy_path))
    # Resolve archive roots from the previous inventory instead of assuming a
    # fixed number of enclosing worktrees.
    repo = Path(identity["trees"]["next"]["path"]).parents[1]
    evidence = {entry["id"]: entry for entry in inventory["evidence"]}
    sources = {}

    def source(label, path, expected=None):
        path = path.resolve()
        sha = digest(path)
        if expected:
            require(sha == expected, f"source hash mismatch: {label}")
        try:
            relative = path.relative_to(repo).as_posix()
        except ValueError:
            relative = path.relative_to(TREE).as_posix()
        sources[label] = {"path": relative, "sha256": sha, "bytes": path.stat().st_size}
        return path

    for label, path in (("inventory", inventory_path), ("identity", identity_path), ("taxonomy", taxonomy_path)):
        source(label, path)
    report_record = next(x for x in identity["declarations"] if x["path"].endswith("cf24-baseline-2026-11-05.md"))
    report_path = source("baseline-report", repo / report_record["path"], report_record["sha256"])
    report_title = report_path.read_text(encoding="utf-8").splitlines()[0]
    report_commit = re.search(r"`([0-9a-f]{7,40})`", report_title)
    require(report_commit is not None, "baseline report has no recorded commit prefix")

    def archive(label):
        item = evidence[label]
        return read(source(label, repo / item["path"], item["sha256"]))

    raw = archive("cf24-u240-baseline.raw")
    review = archive("cf24-u240-baseline.review")
    mechanical = archive("cf24-u240-baseline.mechanical")
    overlap = archive("cf24-u240-baseline.overlap")
    variant = archive("cf24-moved-rule.raw")
    owner = archive("cf24-u240-baseline.index")
    expected_model = identity["u240"]["weight_sha256"]
    require(owner["modelSha256"] == expected_model, "owner model mismatch")
    for obj in (raw, variant):
        require(obj["model"]["files"]["model.safetensors"] == expected_model, "raw model mismatch")
        require(obj["units"]["sha256"] == inventory["cf24_contract_check"]["actual"], "unit hash mismatch")
    # An owning index must actually pin the files, not merely name the model.
    for label in ("cf24-u240-baseline.raw", "cf24-u240-baseline.review", "cf24-u240-baseline.mechanical",
                  "cf24-u240-baseline.overlap", "cf24-moved-rule.raw"):
        expected = sources[label]["sha256"]
        rel = Path(sources[label]["path"]).relative_to(".local/world-components-next-worktree").as_posix()
        require(any(x["path"] == rel and x["sha256"] == expected for x in owner["files"]), f"owner does not pin {label}")

    unit_entry = evidence["cf24-contract"]
    contract_path = source("contract", repo / unit_entry["path"], unit_entry["sha256"])
    units = [json.loads(line) for line in contract_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    next_tree = Path(identity["trees"]["next"]["path"])
    pin_path = source("input-pin", next_tree / "artifacts/next-inputs/pin.json")
    pin = read(pin_path)
    pin_dir = pin_path.parent
    for key in ("world-components/n4-cf24-contract.jsonl", "world-components/n4-cf24-materials-v2.json"):
        source("pinned-" + Path(key).name, pin_dir / key, pin["files"][key]["sha256"])
    require(digest(contract_path) == pin["files"]["world-components/n4-cf24-contract.jsonl"]["sha256"], "local/pinned contract mismatch")
    material = read(pin_dir / "world-components/n4-cf24-materials-v2.json")
    material_index = {s["id"]: (i, s) for i, s in enumerate(material["sources"])}
    require(len(material_index) == len(material["sources"]), "duplicate sourceId in materials")

    raw_index = indexed(raw["rows"], "raw")
    review_index = indexed(review["rows"], "review")
    mech_index = indexed(mechanical["rows"], "mechanical")
    overlap_index = indexed(overlap["records"], "overlap")
    variant_index = indexed(variant["rows"], "variant")
    unit_index = indexed(units, "contract")
    for label, index in (("raw", raw_index), ("review", review_index), ("mechanical", mech_index), ("overlap", overlap_index), ("variant", variant_index)):
        require(set(index) == set(unit_index), f"unit coverage mismatch: {label}")
    actual_added = {r["unitId"] for r in review["rows"] if "added" in r["flags"]}
    require(actual_added == set(taxonomy["added_annotations"]), "unclassified or stale added annotation")

    def finding(category, status, subtype, span, reason, origin):
        return dict(category=category, status=status, subtype=subtype, span=span, reason=reason, origin=origin)

    catalog = []
    moved_pairs = []
    for uid in sorted(unit_index):
        ui, unit = unit_index[uid]
        ri, row = raw_index[uid]
        vi, verdict = review_index[uid]
        mi, machine = mech_index[uid]
        oi, ov = overlap_index[uid]
        xi, changed = variant_index[uid]
        for label, obj in (("raw", row), ("review", verdict), ("mechanical", machine), ("variant", changed), ("overlap", ov)):
            require(obj["sourceId"] == unit["sourceId"] and obj["kind"] == unit["kind"], f"metadata mismatch {uid}: {label}")
        require(row["fact"] == unit["fact"] == changed["fact"], f"fact mismatch {uid}")
        require(row["input"] == row["inputUsed"] == unit["input"] == changed["input"], f"input mismatch {uid}")
        require(verdict["text"] == machine["text"] == row["text"], f"review text mismatch {uid}")
        require((ov["label"] == "independent") == (verdict["independence"] == "independent"), f"independence mismatch {uid}")
        si, fixture = material_index[unit["sourceId"]]
        facts = [(i, f) for i, f in enumerate(fixture["facts"]) if f["factId"] == unit["fact"]["factId"]]
        require(len(facts) == 1 and facts[0][1] == unit["fact"], f"fixture fact mismatch {uid}")
        fi = facts[0][0]
        fact = unit["fact"]
        findings = []
        for flag, detail in verdict["flags"].items():
            if flag == "added":
                spec = taxonomy["added_annotations"][uid]
                span = detail["text"]
                findings.append(finding("extra_action_state", "failed", spec["kind"], span, detail["why"], "archived-assistant-review"))
                for category, key, explanation in (
                    ("subject", "subject_fragment", "病态主语出现在新增尾句；不改判核心人物归属。"),
                    ("position", "position_fragment", "物件可见不授权人物到达后在其旁边站住或停留。"),
                ):
                    if key in spec:
                        findings.append(finding(category, "failed", "added-clause-" + category, spec[key], explanation, "c4-archive-classification"))
            elif flag == "repeated":
                findings.append(finding("repetition", "failed", "duplicate-proposition", detail, "归档标为复述。", "archived-assistant-review"))
            elif flag == "language":
                findings.append(finding("language", "failed", "malformed-wording", row["text"], detail, "archived-assistant-review"))
            else:
                raise ValueError(f"unknown flag {uid}: {flag}")
        scan = taxonomy["direction_scan"]
        if fact["kind"] == scan["kind"] and fact.get("direction") == scan["fact_direction"]:
            for marker in scan["markers"]:
                if marker in row["text"]:
                    findings.append(finding("direction", "undetermined", "level-wording-risk", marker,
                                            "方向=平而写高低词；归档仍支持起终点，不将措辞风险改判方向事实矛盾。", "c4-coverage-scan"))
        if fact["kind"] == "sanity_changed":
            findings.append(finding("sanity_value", "undetermined", "numeric-capability-not-tested", row["text"],
                                    "原事实12→9，inputUsed只写发紧且禁止数值；未测试数值、上升或不变。", "c4-coverage-audit"))
        for item in findings:
            require(item["span"] in row["text"], f"span not in original text: {uid}")
        value_fields = [key for key in ("resultText", "text", "from", "to", "direction") if key in fact]
        provenance = {
            "authority": "registered-offline-fixture; not a committed-world-point",
            "sourceId": unit["sourceId"], "factId": fact["factId"],
            "contract": {"source": "contract", "line": ui + 1, "fieldPaths": [f"/fact/{key}" for key in ("name", *value_fields)]},
            "fixture": {"source": "pinned-n4-cf24-materials-v2.json", "jsonPointer": f"/sources/{si}/facts/{fi}"},
            "entityId": fact.get("entityId"), "pointId": fact.get("pointId"), "worldFieldPath": fact.get("fieldPath"),
            "missingWorldProvenance": [key for key in ("entityId", "pointId", "fieldPath") if key not in fact],
            "note": "字段路径指向冻结夹具，不伪装成世界字段；不按姓名补造ID。",
        }
        record = {
            "caseId": "c4-cf24-" + uid.replace(":", "-"), "unitId": uid, "sourceId": unit["sourceId"], "kind": unit["kind"],
            "fact": fact, "provenance": provenance, "inputUsed": row["inputUsed"], "text": row["text"],
            "generation": {key: row[key] for key in ("complete", "stopReason", "newTokens", "seconds")},
            "archivePointers": {"raw": f"/rows/{ri}", "review": f"/rows/{vi}", "mechanical": f"/rows/{mi}", "overlap": f"/records/{oi}"},
            "archivedReview": verdict, "mechanicalReview": machine, "trainingOverlap": ov,
            "findings": findings, "archivedDefect": bool(verdict["flags"]),
            "retriesThisClassification": 0, "fallback": {"status": "not-run", "reason": "Archive classification, no generation or fallback executed."},
        }
        catalog.append(record)
        if fact["kind"] == "moved":
            rule = variant["variant"]["rule"]
            require(changed["inputUsed"].count(rule) == 1, f"moved rule missing/duplicated {uid}")
            require(changed["inputUsed"].replace(rule + "\n", "") == row["inputUsed"], f"variant changes more than rule {uid}")
            moved_pairs.append({
                "unitId": uid, "caseId": record["caseId"], "fact": fact, "baseline": row,
                "movedRule": changed, "movedRulePointer": f"/rows/{xi}",
                "textChanged": row["text"] != changed["text"],
                "reviewTransfer": "not-transferred" if row["text"] != changed["text"] else "identical-text-only",
                "variantVerdict": "undetermined" if row["text"] != changed["text"] else "see-identical-baseline-text",
                "note": "归档中一次基线、一次提示变体；本轮重试0；不把旧片段标签贴到变体新文本。",
            })
        else:
            require(changed["inputUsed"] == row["inputUsed"], f"non-moved variant input changed {uid}")

    require(len(moved_pairs) == variant["variant"]["unitsChanged"], "variant changed-input count mismatch")

    # Recompute the original summary from per-unit rows, not from prose.
    supported = sum(r["archivedReview"]["factSupported"] for r in catalog)
    flags = {flag: [r["unitId"] for r in catalog if flag in r["archivedReview"]["flags"]] for flag in ("added", "repeated", "language")}
    source_ids = sorted({r["sourceId"] for r in catalog})
    defective = {r["sourceId"] for r in catalog if r["archivedDefect"]}
    independent = [r for r in catalog if r["archivedReview"]["independence"] == "independent"]
    independent_bad_sources = {r["sourceId"] for r in independent if r["archivedDefect"]}
    require(supported == review["summary"]["factsSupported"], "fact summary mismatch")
    require(len(source_ids) - len(defective) == review["summary"]["strictCleanSources"], "clean summary mismatch")
    require(len(source_ids) - len(independent_bad_sources) == review["summary"]["cleanOnIndependentUnits"], "independent summary mismatch")
    for flag, key in (("added", "addedTextUnits"), ("repeated", "repeatedUnits"), ("language", "languageUnits")):
        require(flags[flag] == sorted(review["summary"][key]), f"{flag} summary mismatch")

    categories = {}
    for category, description in taxonomy["categories"].items():
        categories[category] = {
            "description": description,
            "failedUnitIds": [r["unitId"] for r in catalog if any(f["category"] == category and f["status"] == "failed" for f in r["findings"])],
            "undeterminedUnitIds": [r["unitId"] for r in catalog if any(f["category"] == category and f["status"] == "undetermined" for f in r["findings"])],
        }
    summary = {
        "units": len(catalog), "sources": len(source_ids), "kinds": dict(sorted(Counter(r["kind"] for r in catalog).items())),
        "archivedFactSupported": supported, "archivedCoreFactFailures": len(catalog) - supported,
        "archivedDefectiveUnits": sum(r["archivedDefect"] for r in catalog), "archivedFlagUnitIds": flags,
        "archivedFullyCleanSources": len(source_ids) - len(defective),
        "signatureIndependentUnits": len(independent), "signatureIndependentDefectiveUnits": sum(r["archivedDefect"] for r in independent),
        "sourcesWithDefectsOnIndependentUnits": sorted(independent_bad_sources),
        "categories": categories, "movedUnits": len(moved_pairs), "movedRuleChangedOutputs": sum(r["textChanged"] for r in moved_pairs),
        "missingCommittedWorldProvenanceUnits": sum(bool(r["provenance"]["missingWorldProvenance"]) for r in catalog),
        "newGenerations": 0, "newRetries": 0,
    }
    git = subprocess.run(["git", "-c", f"safe.directory={TREE.as_posix()}", "-C", str(TREE), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    run_context = {
        "checkpoint": {"name": "Randeng-T5-77M/u240", "weightSha256": expected_model, "files": raw["model"]["files"]},
        "archivedRun": {key: raw[key] for key in ("purpose", "device", "environment", "decode", "variant", "units")},
        "archivedGenerationCommit": None, "reportedGenerationCommitPrefix": report_commit.group(1),
        "generationCommitNote": "前缀仅来自已核对哈希的baseline-report标题；原始生成文件未绑定提交，不补造完整SHA。",
        "classificationTreeCommit": git.stdout.strip(),
        "classifierSha256": digest(HERE), "taxonomySha256": digest(taxonomy_path),
        "reviewAuthor": review["reviewer"], "newHumanReview": False,
    }
    outputs = {
        "results/cf24-catalog-v1.json": encode({"protocol": "c4-cf24-classification-v1", "context": run_context, "sources": sources, "summary": summary, "rows": catalog}),
        "results/cf24-moved-rule-pairs-v1.json": encode({"protocol": "c4-cf24-moved-archive-pairs-v1", "modelSha256": expected_model, "device": variant["device"], "decode": variant["decode"], "variant": variant["variant"], "sourceRefs": {k: sources[k] for k in ("cf24-u240-baseline.raw", "cf24-moved-rule.raw")}, "rows": moved_pairs}),
    }
    candidates = [r for r in catalog if r["findings"]]
    batch_size = taxonomy["manual_batches"]["max_items"]
    require(0 < batch_size <= 10, "human batches must contain at most 10 cases")
    for start in range(0, len(candidates), batch_size):
        number = start // batch_size + 1
        rows = [{"caseId": r["caseId"], "unitId": r["unitId"], "fact": r["fact"], "provenance": r["provenance"],
                 "inputUsed": r["inputUsed"], "text": r["text"], "archivedReview": r["archivedReview"],
                 "proposedFindings": r["findings"], "humanVerdict": None, "humanNotes": None} for r in candidates[start:start + batch_size]]
        outputs[f"review/batch-{number:02d}.json"] = encode({"protocol": "c4-human-review-candidates-v1", "status": "pending-human-review", "batchId": f"c4-cf24-{number:02d}", "modelSha256": expected_model, "rows": rows})

    lines = [
        "# c4：cf24 失败分类 v1", "",
        "支持 R11 / narration N4。档位：**有归档分析结果**；没有新推理、训练或接线。", "",
        "冻结 cf24 输入交给 u240 的旧 CPU 贪心运行产生原文，旧 assistant 判读给出逐条标签；",
        "本脚本按 unitId 连接原文、判读、机械判分、训练重叠和冻结夹具，分类并保留原标签。",
        "本轮没有真人核验；review/batch-*.json 是待核验清单。", "",
        "## 已证明：归档里记录了什么", "",
        f"逐条连接 {len(catalog)} 单元 / {len(source_ids)} 源；归档 factSupported={supported}。这不是本轮重新证明模型事实正确。",
        f"原标签缺陷 {summary['archivedDefectiveUnits']} 条：新增 {len(flags['added'])}、复述 {len(flags['repeated'])}、语病 {len(flags['language'])}；全干净源 {summary['archivedFullyCleanSources']}。",
        f"签名独立 {len(independent)} 条，其中缺陷 {summary['signatureIndependentDefectiveUnits']} 条；签名独立不等于新场景或短语独立。", "",
        "## 已失败：分类到原文", "",
        "分类可重叠。subject 指鞋底充当新增小句的主语，不改判为核心人物互换。position 指额外停留，物件出现在可见列表不授权停留。", "",
        "| 类别 | 已失败单元 | 无法判断单元 |", "|---|---|---|",
    ]
    for key, info in categories.items():
        lines.append(f"| {key} | {', '.join(info['failedUnitIds']) or '无已登记失败'} | {', '.join(info['undeterminedUnitIds']) or '—'} |")
    lines += ["", "输入、事实、输出原文、原始路径和耗时详见 results/cf24-catalog-v1.json。待人工核验按以下批次拆分，当前均为pending：", ""]
    for start in range(0, len(candidates), batch_size):
        number = start // batch_size + 1
        batch = candidates[start:start + batch_size]
        lines.append(f"- review/batch-{number:02d}.json（{len(batch)}条）：" + "、".join(r["unitId"] for r in batch))
    lines += [
        "", "## 无法判断：覆盖与来源缺口", "",
        "- 关系双方互换没有专门样本；移动起终点是另一维度，不以起终点正确替代关系方向验收。",
        "- 移动10条，direction均为平；上升、下降未覆盖。t14:f0和t18:f0的“上来”仅列措辞风险，原factSupported不变。",
        "- 理智仅t10:f3和t16:f2，都是12→9，实际输入只写“发紧”、禁止数值；不能验证数值保真、上升和不变。",
        f"- {summary['missingCommittedWorldProvenanceUnits']}条缺entityId/pointId/世界fieldPath。记录冻结contract行号和materials JSON指针，保留缺失值，不按姓名造ID。可复核旧夹具，但不能据此冒充已提交世界点或新的独立验收。",
        "- 归档reviewer明确为assistant；标题里“人工”不能当作真人签字。新核验状态一律pending。", "",
        "## 旧提示变体与重试、回退", "",
        f"results/cf24-moved-rule-pairs-v1.json保存全部{len(moved_pairs)}条移动的基线/提示变体原文和实际输入；其中{summary['movedRuleChangedOutputs']}条输出变化。",
        "变体仅在10条移动输入插入归档提示，其余75条输入逐字相同；变化后的文本不继承旧片段判读，结论记undetermined。",
        "旧文件各记录一次基线与一次提示变体；没有完整尝试历史，不能声称仅尝试过两次。本轮新增生成0、重试0、未执行回退。", "",
        "## 运行身份、速度与复跑", "",
        f"权重sha256：`{expected_model}`。原文来自CPU/4线程的贪心运行，EOS或20秒预算；每条seconds/newTokens保存在catalog中。",
        "本轮只做文件分析，不把旧seconds当作本轮推理速度，不与CUDA探针混比。原生成完整SHA缺失；旧报告仅给43d897b前缀，分类HEAD、脚本哈希、输入哈希在context/sources中。", "",
        "```powershell", "python -X utf8 scripts/classify_cf24.py", "python -X utf8 scripts/classify_cf24.py --check", "```", "",
        "来源哈希、每条连接、输入不变性和归档summary均通过后才写结果；--check只读核对生成文件。review清单不承载已完成的人类判定，真人反馈应另存文件。", "",
        "## 可单独阅读的结论", "",
        "当前明确的旧失败是新增动作/状态、复述和语病；没有证据把这些改写成主体互换或理智数值错误。",
        "这份分类完成诊断材料整理，不能宣告模型泛化通过。后续对照必须固定u240身份，用登记的独立输入验收，不能围绕这些旧句子删尾或打补丁后宣称新场景有效。",
        "证据：results/cf24-catalog-v1.json、results/cf24-moved-rule-pairs-v1.json、freeze/failure-classification-v1.json。", "",
    ]
    outputs["results/failure-report-v1.md"] = "\n".join(lines)
    manifest = {"protocol": "c4-failure-classification-freeze-v1", "context": run_context, "sources": sources,
                "summary": summary, "artifacts": {name: hashlib.sha256(body.encode("utf-8")).hexdigest() for name, body in outputs.items()},
                "validation": ["source hashes and owner index pins", "one-to-one unitId joins", "fixture facts equal raw facts",
                               "review text equals raw text", "original inputs and variant insertion", "archived summary recomputed", "all finding spans quoted from original text"]}
    outputs["freeze/failure-classification-v1.json"] = encode(manifest)
    for relative, body in outputs.items():
        target = TASK / relative
        if args.check:
            require(target.read_bytes() == body.encode("utf-8"), f"generated artifact mismatch: {relative}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body.encode("utf-8"))
    print(encode({"mode": "checked" if args.check else "written", "units": len(catalog), "archivedDefects": summary["archivedDefectiveUnits"],
                  "manualCandidates": len(candidates), "batches": (len(candidates) + batch_size - 1) // batch_size,
                  "artifacts": list(outputs), "categories": categories}))


if __name__ == "__main__":
    main()
