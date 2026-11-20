"""生成独立评审材料（不覆盖执行方初审）。

- step5/independent-review/clause-review.jsonl：72 条分句，decision/sourceId/reason 留空，
  不含初审标签，避免锚定。
- step5/independent-review/naturalness-return.json：十题遮蔽文本，choice/reason 留空。
- step5/independent-review/README.md：流程与改判记录规则。

用法（仓库根）：
  /d/software/Anaconda/envs/nndl_proj/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/build_independent_review.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RES = HERE / "step5/independent-review"
CLAUSES = HERE / "step5/clauses.jsonl"
BALLOT = HERE / "step4/ballot/ballot.json"


def main():
    RES.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in CLAUSES.read_text(encoding="utf-8").splitlines()]
    template = [{"sampleId": r["sampleId"], "arm": r["arm"],
                 "clauseIndex": r["clauseIndex"], "clause": r["clause"],
                 "decision": None, "sourceId": [], "reason": ""} for r in rows]
    (RES / "clause-review.jsonl").write_text(
        "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in template), encoding="utf-8")

    ballot = json.loads(BALLOT.read_text(encoding="utf-8"))
    ret = {"question": ballot["question"], "optionNoDifference": ballot["optionNoDifference"],
           "seed": ballot["seed"], "note": "评审者只依据 step5/review-packet.md 填写；映射在提交后揭示。",
           "items": [{**{k: item[k] for k in ("sampleId", "programOnly", "options")},
                      "choice": None, "reason": None} for item in ballot["items"]]}
    (RES / "naturalness-return.json").write_text(
        json.dumps(ret, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    readme = """# 独立评审（与执行方初审分开）

## 边界

- 执行方初审：`step5/clauses.jsonl`、`step5/adjudication.json`、`step5/summary.md`。**只读，不改。**
- 独立评审记录写在本目录，不覆盖初审；改判写 `differences.md`，保留理由。
- 自然度评审者只看 `step5/review-packet.md`；提交选票前不提供 `step4/ballot/order.json`、`step4/scores.json`、`step5/clauses.jsonl`。

## 分句事实核验

1. 打开 `clause-review.jsonl`，逐行填 `decision`（`supported` / `unsupported` / `undetermined`）、`sourceId`、`reason`。
2. `sourceId` 只写实际依赖的来源：`initial.*` / `after.*` 字段路径、素材来源 ID（`item:` `loc:` `char:` `program:`）或 `delta.*`。
   自动候选只在 `step5/clauses.jsonl` 里，供执行方使用；独立评审请自行核对状态，不要照抄候选。
3. 判据：句子断言能否从已提交状态、Δ 或授权素材逐项找到来源；任务目标、物品可见不授权新动作。
4. 与初审不一致的，在 `differences.md` 按“分句 → 初审结论 → 独立结论 → 理由”登记。

## 自然度

1. 只读 `step5/review-packet.md`，按题填写 `naturalness-return.json` 的 `choice`（`甲`/`乙`/`丙`/`看不出差别`）与可选 `reason`。
2. 十题全部作答后再提交；提交前不打开映射。
3. 提交后由执行方运行 `reveal_naturalness.py` 揭示 `order.json` 映射并统计（缺答会拒绝统计）。

## 门槛

有效配对 6 题（四题仅程序输出）＜10，自然度门槛维持 `not_evaluable`；独立评审完成也不改变该状态，只能补充“六题配对内的比较”。
"""
    (RES / "README.md").write_text(readme, encoding="utf-8")
    print("clauses", len(template), "ballot items", len(ret["items"]), "dir", RES)


if __name__ == "__main__":
    main()
