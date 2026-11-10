"""选票提交后揭示遮蔽映射并统计（不修改选票与映射原文件）。

用法（仓库根）：
  /d/software/Anaconda/envs/nndl_proj/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/reveal_naturalness.py

要求：naturalness-return.json 十题全部有 choice；否则报错退出，不统计。
输出：step5/independent-review/naturalness-result.json
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RES = HERE / "step5/independent-review"
ORDER = HERE / "step4/ballot/order.json"
LABELS = ["甲", "乙", "丙"]
VALID = {"ns-appear-1", "ns-loc-appear-1", "ns-pers-1", "ns-multi-1",
         "ns-cont-1", "ns-cont-2"}


def main():
    ret = json.loads((RES / "naturalness-return.json").read_text(encoding="utf-8"))
    order = json.loads(ORDER.read_text(encoding="utf-8"))
    missing = [i["sampleId"] for i in ret["items"] if i["choice"] in (None, "")]
    if missing:
        raise SystemExit(f"还有 {len(missing)} 题未作答：{missing}")

    rows, tally = [], {"A": 0, "B": 0, "C": 0, "no_difference": 0}
    for item in ret["items"]:
        sid = item["sampleId"]
        perm = order["permutations"][sid]
        choice = item["choice"]
        if choice == ret["optionNoDifference"]:
            arm = "no_difference"
        else:
            arm = perm[LABELS.index(choice)]
        row = {"sampleId": sid, "programOnly": item["programOnly"],
               "choice": choice, "arm": arm, "validPair": sid in VALID}
        rows.append(row)
        if sid in VALID:
            tally[arm] += 1

    valid_count = sum(r["validPair"] for r in rows)
    result = {"validPairs": valid_count, "tallyOnValidPairs": tally,
              "gate": "not_evaluable" if valid_count < 10 else
                      ("pass" if tally["B"] + tally["C"] >= 7 and tally["A"] == 0
                       else "fail"),
              "gateNote": "有效配对不足十题时按冻结协议记 not_evaluable，不降分母、不改阈值",
              "rows": rows}
    (RES / "naturalness-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("validPairs", "tallyOnValidPairs", "gate")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
